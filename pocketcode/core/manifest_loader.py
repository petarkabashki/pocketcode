from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml

logger = logging.getLogger(__name__)

SUPPORTED_SCHEMA_VERSIONS: frozenset = frozenset({1})
PLUGIN_YAML = "plugin.yaml"
AGENT_YAML = "agent.yaml"

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

_LEGACY_SECTIONS = ("components", "workflows", "node_definitions", "flows", "modes")


class ManifestSchemaError(ValueError):
    """Raised when schema_version is absent or unrecognised."""


@dataclass
class ParsedManifest:
    schema_version: int
    name: str
    description: str
    plugin_root: Path
    tools: Dict[str, str] = field(default_factory=dict)
    agents: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    prompts: Dict[str, str] = field(default_factory=dict)
    llm_profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)


def load_manifest(path: Path) -> ParsedManifest:
    """
    Load and validate a plugin manifest.

    Raises ``ManifestSchemaError`` for hard failures (missing/unknown schema_version).
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
        schema_version=int(raw["schema_version"]),
        name=str(raw.get("name") or path.parent.name),
        description=str(raw.get("description", "")),
        plugin_root=path.parent,
        tools=_expect_str_dict(raw.get("tools"), "tools", path),
        agents=_expect_agent_dict(raw.get("agents"), path),
        prompts=_expect_str_dict(raw.get("prompts"), "prompts", path),
        llm_profiles=_expect_nested_dict(raw.get("llm_profiles"), "llm_profiles", path),
    )


def _validate_schema_version(raw: dict, path: Path) -> None:
    """Raise ManifestSchemaError if schema_version is absent or not in the supported set."""
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


def _warn_legacy_sections(raw: dict, path: Path) -> None:
    """Emit WARNING for each legacy section found in a v1 manifest."""
    for key in _LEGACY_SECTIONS:
        if key in raw:
            logger.warning(
                "LEGACY SECTION: plugin manifest '%s' contains '%s:' which is "
                "ignored in schema_version 1. Migration: "
                "- 'components:' (kind=agent) → 'agents:' block with module+entry_fn. "
                "- 'components:' (kind=workflow) → new agent with PocketFlow Flow factory. "
                "- 'workflows:' list → PocketFlow agent in 'agents:' block. "
                "- 'node_definitions:' → remove; PocketFlow Node subclasses own their logic.",
                path,
                key,
            )


def _load_agent_yaml_with_warning(path: Path) -> ParsedManifest:
    """Load a legacy agent.yaml with a deprecation warning and best-effort migration."""
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
        for t in tools_list
        if isinstance(t, dict) and "id" in t and "handler" in t
    }

    # agent.yaml has no module/entry_fn — emit a second targeted warning
    logger.warning(
        "LEGACY MANIFEST: '%s' has no 'module:' or 'entry_fn:' for its agent. "
        "The agent '%s' will NOT be registered as a PocketFlow Flow. "
        "Add agents: block with module+entry_fn to complete migration.",
        path,
        plugin_name,
    )

    return ParsedManifest(
        schema_version=0,  # sentinel: marks shim-loaded manifests
        name=plugin_name,
        description=str(raw.get("description", "")),
        plugin_root=path.parent,
        tools=tools_dict,
        agents={},  # cannot synthesise without entry_fn
        prompts={"system": system_prompt_file} if system_prompt_file else {},
        llm_profiles={},
    )


# ── Helper validators ─────────────────────────────────────────────────────────


def _expect_str_dict(value: Any, section: str, path: Path) -> Dict[str, str]:
    """Return value as Dict[str, str], logging a warning and returning {} on type error."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        logger.warning(
            "Plugin manifest '%s': section '%s' must be a mapping, got %s — ignoring.",
            path,
            section,
            type(value).__name__,
        )
        return {}
    result: Dict[str, str] = {}
    for k, v in value.items():
        if not isinstance(k, str) or not isinstance(v, str):
            logger.warning(
                "Plugin manifest '%s': section '%s' entry %r → %r is not str:str — skipping.",
                path,
                section,
                k,
                v,
            )
            continue
        result[k] = v
    return result


def _expect_agent_dict(value: Any, path: Path) -> Dict[str, Dict[str, Any]]:
    """Return agents section as Dict[str, Dict[str, Any]], validating module+entry_fn."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        logger.warning(
            "Plugin manifest '%s': section 'agents' must be a mapping, got %s — ignoring.",
            path,
            type(value).__name__,
        )
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for agent_name, agent_cfg in value.items():
        if not isinstance(agent_name, str):
            logger.warning(
                "Plugin manifest '%s': agents key %r is not a string — skipping.", path, agent_name
            )
            continue
        if not isinstance(agent_cfg, dict):
            logger.warning(
                "Plugin manifest '%s': agent '%s' config must be a mapping — skipping.",
                path,
                agent_name,
            )
            continue
        # Validate required fields: module + entry_fn
        missing = [f for f in ("module", "entry_fn") if not agent_cfg.get(f)]
        if missing:
            raise ManifestSchemaError(
                f"Agent '{agent_name}' in '{path}' is missing required field(s): "
                + ", ".join(f"'{f}'" for f in missing)
                + ". Both 'module' and 'entry_fn' are required."
            )
        result[agent_name] = dict(agent_cfg)
    return result


def _expect_nested_dict(value: Any, section: str, path: Path) -> Dict[str, Dict[str, Any]]:
    """Return a nested mapping, logging a warning and returning {} on type error."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        logger.warning(
            "Plugin manifest '%s': section '%s' must be a mapping, got %s — ignoring.",
            path,
            section,
            type(value).__name__,
        )
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for k, v in value.items():
        if not isinstance(k, str):
            continue
        if not isinstance(v, dict):
            logger.warning(
                "Plugin manifest '%s': section '%s' entry %r must be a mapping — skipping.",
                path,
                section,
                k,
            )
            continue
        result[k] = dict(v)
    return result
