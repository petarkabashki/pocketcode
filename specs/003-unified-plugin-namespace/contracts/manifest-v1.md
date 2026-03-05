# Contract: Plugin Manifest v1 — Schema-Aware Loader Design

**Date**: 2026-03-05 | **Feature**: 003-unified-plugin-namespace | **Status**: Approved

---

## 1. Unified `plugin.yaml` v1 — Canonical Structure

```yaml
schema_version: 1                 # REQUIRED int; hard error if absent or unknown
name: coder
description: Expert developer focused on implementation and coding tasks.

tools:                            # dict: local_name → dotted.import.Path or file.py:ClassName
  write_to_file: tools/filesystem.py:WriteToFileTool
  git_diff: tools/git.py:GitDiffTool

agents:                           # dict: agent_name → definition block
  coder:
    description: Code implementation specialist.
    module: agents/coder_agent.py  # path relative to plugin root
    entry_fn: create_flow          # zero-arg factory → returns PocketFlow Flow
    llm_profile: gemini_default
    tools:
      - write_to_file              # local name; resolved to this plugin first
      - core.read_file             # qualified cross-plugin reference
    prompts:
      system: prompts/system.md

prompts:                          # dict: prompt_name → file path (relative to plugin root)
  system: prompts/system.md

llm_profiles:                     # dict: profile_name → provider config
  gemini_default:
    provider: gemini
    model: gemini-2.0-flash
```

**Rules**: `schema_version` MUST be the first key. `tools` values are either
`module.ClassName` (importable) or `relative/path.py:ClassName` (file-relative to
plugin root). `agents[*].module` + `agents[*].entry_fn` are both required for every
agent entry.

---

## 2. Python Types & Loader Signature

```python
# pocketcode/core/manifest_loader.py
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml

logger = logging.getLogger(__name__)

SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})
PLUGIN_YAML = "plugin.yaml"
AGENT_YAML  = "agent.yaml"


class ManifestSchemaError(ValueError):
    """Raised when schema_version is absent or unrecognised."""


@dataclass
class ParsedManifest:
    schema_version: int
    name: str
    description: str
    plugin_root: Path
    tools:        Dict[str, str]              = field(default_factory=dict)
    agents:       Dict[str, Dict[str, Any]]   = field(default_factory=dict)
    prompts:      Dict[str, str]              = field(default_factory=dict)
    llm_profiles: Dict[str, Dict[str, Any]]  = field(default_factory=dict)


def load_manifest(path: Path) -> ParsedManifest:
    """
    Load and validate a plugin manifest.

    Raises ManifestSchemaError for hard failures (missing/unknown schema_version).
    Emits WARNING-level log records for migration-required situations (agent.yaml,
    legacy sections). Never silently maps unrecognised formats.
    """
    path = path.resolve()

    # ── agent.yaml detection ──────────────────────────────────────────────────
    if path.name == AGENT_YAML:
        return _load_agent_yaml_with_warning(path)

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ManifestSchemaError(f"Manifest must be a YAML mapping: {path}")

    # ── schema_version validation ─────────────────────────────────────────────
    _validate_schema_version(raw, path)

    # ── legacy section warnings ───────────────────────────────────────────────
    _warn_legacy_sections(raw, path)

    return ParsedManifest(
        schema_version = int(raw["schema_version"]),
        name           = str(raw.get("name") or path.parent.name),
        description    = str(raw.get("description", "")),
        plugin_root    = path.parent,
        tools          = _expect_str_dict(raw.get("tools"), "tools", path),
        agents         = _expect_agent_dict(raw.get("agents"), path),
        prompts        = _expect_str_dict(raw.get("prompts"), "prompts", path),
        llm_profiles   = _expect_nested_dict(raw.get("llm_profiles"), "llm_profiles", path),
    )
```

---

## 3. `schema_version` Validation

```python
def _validate_schema_version(raw: dict, path: Path) -> None:
    if "schema_version" not in raw:
        raise ManifestSchemaError(
            f"'schema_version' is required but missing in {path}. "
            f"Add 'schema_version: 1' as the first key."
        )
    v = raw["schema_version"]
    if not isinstance(v, int) or v not in SUPPORTED_SCHEMA_VERSIONS:
        raise ManifestSchemaError(
            f"Unsupported schema_version={v!r} in {path}. "
            f"Supported versions: {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )
```

**Behaviour**: Both cases are hard errors — the caller (PluginManager) catches
`ManifestSchemaError`, logs at `ERROR` level, and skips the plugin entirely.
No partial load is attempted.

---

## 4. `agent.yaml` Detection & Migration Warning

```python
MIGRATION_GUIDE = """\
    Migrate '{path}' to 'plugin.yaml' with schema_version: 1:
      1. Rename the file to plugin.yaml.
      2. Add 'schema_version: 1' as the first key.
      3. Move personality.system_prompt → prompts.system.
      4. Convert tools list → tools dict (local_name: file.py:Class).
      5. Create an agents: block with 'module:' + 'entry_fn:' pointing to a
         zero-arg Python factory that returns a PocketFlow Flow.
      6. Remove the 'workflows:' list — express as a PocketFlow agent instead.
    See specs/003-unified-plugin-namespace/contracts/manifest-v1.md for the full schema."""


def _load_agent_yaml_with_warning(path: Path) -> ParsedManifest:
    logger.warning(
        "LEGACY MANIFEST: '%s' uses the deprecated 'agent.yaml' format. "
        "It will be loaded via compatibility shim for ONE release cycle, "
        "then rejected. %s",
        path,
        MIGRATION_GUIDE.format(path=path),
    )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _migrate_agent_yaml(raw, path)


def _migrate_agent_yaml(raw: dict, path: Path) -> ParsedManifest:
    """Best-effort migration shim. Maps agent.yaml fields to ParsedManifest."""
    plugin_name = str(raw.get("name") or path.parent.name)
    personality = raw.get("personality", {})
    system_prompt_file = personality.get("system_prompt", "")

    tools_list = raw.get("tools", [])
    tools_dict = {
        t["id"]: f"tools/{t['handler']}"
        for t in tools_list if isinstance(t, dict) and "id" in t and "handler" in t
    }

    # agent.yaml has no module/entry_fn — emit a second targeted warning
    logger.warning(
        "LEGACY MANIFEST: '%s' has no 'module:' or 'entry_fn:' for its agent. "
        "The agent '%s' will NOT be registered as a PocketFlow Flow. "
        "Add agents: block with module+entry_fn to complete migration.",
        path, plugin_name,
    )

    return ParsedManifest(
        schema_version = 0,          # sentinel: marks shim-loaded manifests
        name           = plugin_name,
        description    = str(raw.get("description", "")),
        plugin_root    = path.parent,
        tools          = tools_dict,
        agents         = {},          # cannot synthesise without entry_fn
        prompts        = {"system": system_prompt_file} if system_prompt_file else {},
        llm_profiles   = {},
    )
```

---

## 5. Legacy `components:` and `workflows:` Handling

Both sections existed in the core `plugin.yaml` as pre-namespace relics.

```python
_LEGACY_SECTIONS = ("components", "workflows", "node_definitions", "flows", "modes")

def _warn_legacy_sections(raw: dict, path: Path) -> None:
    for key in _LEGACY_SECTIONS:
        if key in raw:
            logger.warning(
                "LEGACY SECTION: plugin manifest '%s' contains '%s:' which is "
                "ignored in schema_version 1. Migration: "
                "- 'components:' (kind=agent) → 'agents:' block with module+entry_fn. "
                "- 'components:' (kind=workflow) → new agent with PocketFlow Flow factory. "
                "- 'workflows:' list → PocketFlow agent in 'agents:' block. "
                "- 'node_definitions:' → remove; PocketFlow Node subclasses own their logic.",
                path, key,
            )
```

`node_definitions` is also ignored: PocketFlow `Node` subclasses carry their own
kind/behaviour; there is no external registry of node types in v1.

---

## Caller Contract (PluginManager integration)

```python
# In PluginManager._load_plugin():
from pocketcode.core.manifest_loader import load_manifest, ManifestSchemaError

def _load_plugin(self, plugin_root: Path) -> None:
    manifest_path = (
        plugin_root / "agent.yaml"
        if (plugin_root / "agent.yaml").is_file()
        else plugin_root / "plugin.yaml"
    )
    try:
        manifest = load_manifest(manifest_path)
    except ManifestSchemaError as exc:
        logger.error("Skipping plugin at %s: %s", plugin_root, exc)
        return

    # schema_version == 0 → shim-loaded; agents dict will be empty; continue
    # to register tools/prompts but skip Flow registration
    ...
```

---

## Decision Log

| Decision | Rationale |
|---|---|
| `ManifestSchemaError` is a `ValueError` subclass | Keeps it catchable as a broad `Exception` by existing PluginManager try/except, while remaining targetable by test assertions. |
| `agent.yaml` shim returns `schema_version=0` sentinel | Allows callers to branch on shim vs native load without inspecting the filename again. |
| `node_definitions:` treated as legacy (warn + ignore) | FR-012 eliminates the node registry concept; PocketFlow Nodes are self-describing Python classes. |
| Migration warning uses `logger.warning`, not `warnings.warn` | Stays consistent with FR-009 / spec requirement that all observability goes through Python `logging` to stderr. |
