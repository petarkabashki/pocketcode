from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml

from pocketcode.core.reference_syntax import (
    normalize_prompt_source,
    normalize_registry_reference,
    validate_prompt_source,
    validate_registry_reference,
)

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
      5. Create a flows: block with 'module:' + 'entry_fn:' pointing to a
            zero-arg Python factory in flows/<name>.py that returns a PocketFlow Flow.
        6. Optionally add agents/*.yaml files for composite runtime agents that target those flows.
        7. Remove the 'workflows:' list — express orchestration as a PocketFlow Flow instead.
    See specs/003-unified-plugin-namespace/contracts/manifest-v1.md for the full schema."""

_LEGACY_SECTIONS = ("components", "workflows", "node_definitions", "modes")


class ManifestSchemaError(ValueError):
    """Raised when schema_version is absent or unrecognised."""


@dataclass
class ParsedManifest:
    schema_version: int
    name: str
    description: str
    plugin_root: Path
    tools: Dict[str, str] = field(default_factory=dict)
    flows: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    prompts: Dict[str, str] = field(default_factory=dict)
    llm_profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def agents(self) -> Dict[str, Dict[str, Any]]:
        """Backward-compatible alias for flow manifests."""
        return self.flows


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

    raw_flows = raw.get("flows")
    raw_agents = raw.get("agents")
    if raw_flows is not None and raw_agents is not None:
        logger.warning(
            "Plugin manifest '%s' declares both 'flows' and legacy 'agents'. Using 'flows'.",
            path,
        )

    return ParsedManifest(
        schema_version=int(raw["schema_version"]),
        name=str(raw.get("name") or path.parent.name),
        description=str(raw.get("description", "")),
        plugin_root=path.parent,
        tools=_expect_str_dict(raw.get("tools"), "tools", path),
        flows=_expect_flow_dict(raw_flows if raw_flows is not None else raw_agents, path),
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
                "- 'components:' (kind=agent) → 'flows:' block with module+entry_fn. "
                "- 'components:' (kind=workflow) → new agent with PocketFlow Flow factory. "
                "- 'workflows:' list → PocketFlow agent in 'flows:' block. "
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
        "LEGACY MANIFEST: '%s' has no 'module:' or 'entry_fn:' for its flow. "
        "The legacy agent '%s' will NOT be registered as a PocketFlow Flow. "
        "Add flows: block with module+entry_fn to complete migration.",
        path,
        plugin_name,
    )

    return ParsedManifest(
        schema_version=0,  # sentinel: marks shim-loaded manifests
        name=plugin_name,
        description=str(raw.get("description", "")),
        plugin_root=path.parent,
        tools=tools_dict,
        flows={},  # cannot synthesise without entry_fn
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


def _expect_flow_dict(value: Any, path: Path) -> Dict[str, Dict[str, Any]]:
    """Return flows section as Dict[str, Dict[str, Any]], validating module+entry_fn."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        logger.warning(
            "Plugin manifest '%s': section 'flows' must be a mapping, got %s — ignoring.",
            path,
            type(value).__name__,
        )
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for flow_name, flow_cfg in value.items():
        if not isinstance(flow_name, str):
            logger.warning(
                "Plugin manifest '%s': flows key %r is not a string — skipping.", path, flow_name
            )
            continue
        if not isinstance(flow_cfg, dict):
            logger.warning(
                "Plugin manifest '%s': flow '%s' config must be a mapping — skipping.",
                path,
                flow_name,
            )
            continue
        # Validate required fields: module + entry_fn
        markdown_ref = flow_cfg.get("markdown") or flow_cfg.get("markdown_file")
        source_ref = flow_cfg.get("source")
        has_markdown_source = isinstance(markdown_ref, str) and markdown_ref.strip()
        if not has_markdown_source and isinstance(source_ref, str) and source_ref.strip().lower().endswith(".md"):
            has_markdown_source = True

        missing = [f for f in ("module", "entry_fn") if not flow_cfg.get(f)]
        if missing and not has_markdown_source:
            raise ManifestSchemaError(
                f"Flow '{flow_name}' in '{path}' is missing required field(s): "
                + ", ".join(f"'{f}'" for f in missing)
                + ". Both 'module' and 'entry_fn' are required."
            )
        _validate_flow_reference_fields(flow_name, flow_cfg, path)
        result[flow_name] = dict(flow_cfg)
    return result


def _validate_flow_reference_fields(flow_name: str, flow_cfg: Dict[str, Any], path: Path) -> None:
    tools = flow_cfg.get("tools")
    if isinstance(tools, list):
        for index, tool_ref in enumerate(tools):
            if not isinstance(tool_ref, str):
                continue
            if tool_ref.strip() == "*":
                continue
            _validate_manifest_ref(
                validate_registry_reference,
                tool_ref,
                field_name=f"flows.{flow_name}.tools[{index}]",
                path=path,
                allowed_kinds={"tool"},
            )

    prompt_files = flow_cfg.get("prompt_files")
    if prompt_files is None and isinstance(flow_cfg.get("prompts"), list):
        prompt_files = flow_cfg.get("prompts")
    if isinstance(prompt_files, list):
        for index, prompt_ref in enumerate(prompt_files):
            if not isinstance(prompt_ref, str):
                continue
            _validate_manifest_ref(
                validate_prompt_source,
                prompt_ref,
                field_name=f"flows.{flow_name}.prompt_files[{index}]",
                path=path,
            )

    handoff_agents = flow_cfg.get("handoff_agents")
    if isinstance(handoff_agents, list):
        for index, handoff_ref in enumerate(handoff_agents):
            if not isinstance(handoff_ref, str):
                continue
            _validate_manifest_ref(
                validate_registry_reference,
                handoff_ref,
                field_name=f"flows.{flow_name}.handoff_agents[{index}]",
                path=path,
                allowed_kinds={"agent", "flow"},
            )

    raw_default_agent = flow_cfg.get("default_agent") or flow_cfg.get("default_agent_profile")
    if isinstance(raw_default_agent, dict):
        default_tools = raw_default_agent.get("tools")
        if isinstance(default_tools, list):
            for index, tool_ref in enumerate(default_tools):
                if not isinstance(tool_ref, str):
                    continue
                _validate_manifest_ref(
                    validate_registry_reference,
                    tool_ref,
                    field_name=f"flows.{flow_name}.default_agent.tools[{index}]",
                    path=path,
                    allowed_kinds={"tool"},
                )
        extra_prompts = raw_default_agent.get("extra_prompts")
        if isinstance(extra_prompts, list):
            for index, prompt_ref in enumerate(extra_prompts):
                if not isinstance(prompt_ref, str):
                    continue
                _validate_manifest_ref(
                    validate_prompt_source,
                    prompt_ref,
                    field_name=f"flows.{flow_name}.default_agent.extra_prompts[{index}]",
                    path=path,
                )

    composite_agents = (
        flow_cfg.get("composite_agents")
        or flow_cfg.get("sub_agents")
        or flow_cfg.get("delegate_agents")
    )
    if isinstance(composite_agents, list):
        for index, composite_ref in enumerate(composite_agents):
            if not isinstance(composite_ref, str):
                continue
            _validate_manifest_ref(
                validate_registry_reference,
                composite_ref,
                field_name=f"flows.{flow_name}.composite_agents[{index}]",
                path=path,
                allowed_kinds={"agent", "flow"},
            )

    _normalize_flow_reference_fields(flow_cfg)


def _normalize_flow_reference_fields(flow_cfg: Dict[str, Any]) -> None:
    _normalize_registry_ref_list(flow_cfg, "tools", allowed_kinds={"tool"}, preserve_wildcard=True)
    _normalize_registry_ref_list(flow_cfg, "handoff_agents", allowed_kinds={"agent", "flow"})
    _normalize_registry_ref_list(flow_cfg, "composite_agents", allowed_kinds={"agent", "flow"})
    _normalize_registry_ref_list(flow_cfg, "sub_agents", allowed_kinds={"agent", "flow"})
    _normalize_registry_ref_list(flow_cfg, "delegate_agents", allowed_kinds={"agent", "flow"})

    if isinstance(flow_cfg.get("prompt_files"), list):
        _normalize_prompt_source_list(flow_cfg, "prompt_files")
    if isinstance(flow_cfg.get("prompts"), list):
        _normalize_prompt_source_list(flow_cfg, "prompts")

    raw_default_agent = flow_cfg.get("default_agent") or flow_cfg.get("default_agent_profile")
    if isinstance(raw_default_agent, dict):
        _normalize_registry_ref_list(raw_default_agent, "tools", allowed_kinds={"tool"})
        _normalize_prompt_source_list(raw_default_agent, "extra_prompts")


def _normalize_registry_ref_list(
    mapping: Dict[str, Any],
    key: str,
    *,
    allowed_kinds: set[str],
    preserve_wildcard: bool = False,
) -> None:
    raw_values = mapping.get(key)
    if not isinstance(raw_values, list):
        return

    normalized: list[Any] = []
    for value in raw_values:
        if not isinstance(value, str):
            normalized.append(value)
            continue
        candidate = value.strip()
        if preserve_wildcard and candidate == "*":
            normalized.append("*")
            continue
        normalized.append(normalize_registry_reference(candidate, allowed_kinds=allowed_kinds))
    mapping[key] = normalized


def _normalize_prompt_source_list(mapping: Dict[str, Any], key: str) -> None:
    raw_values = mapping.get(key)
    if not isinstance(raw_values, list):
        return

    normalized: list[Any] = []
    for value in raw_values:
        if not isinstance(value, str):
            normalized.append(value)
            continue
        normalized.append(normalize_prompt_source(value))
    mapping[key] = normalized


def _validate_manifest_ref(validator: Any, ref: str, *, field_name: str, path: Path, **kwargs: Any) -> None:
    try:
        validator(ref, field_name=field_name, **kwargs)
    except ValueError as exc:
        raise ManifestSchemaError(f"{path}: {exc}") from exc


_expect_agent_dict = _expect_flow_dict


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
