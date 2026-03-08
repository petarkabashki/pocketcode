"""CompositeAgentManager — loads, indexes, and persists composite agent objects.

Load order (highest precedence first within same name):
    1. Plugin-provided agent YAML (``agents/*.yaml``) or inline ``default_agent``
    2. Workspace-local file (``.pocketcode/agents/<name>.yaml``)
    3. Synthesised default (built from FlowDefinition top-level fields)

A WARNING is logged on any name collision, identifying both conflicting sources.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from pocketcode.core.discovery_rules import DiscoveryFilter
from pocketcode.core.reference_syntax import (
    normalize_prompt_source,
    normalize_registry_reference,
    validate_prompt_source,
    validate_registry_reference,
)
from pocketcode.core.resource_roots import (
    ResourceRoot,
    discover_resource_roots,
    primary_resource_root,
    resource_root_for_path,
)

logger = logging.getLogger(__name__)


class CompositeAgentManager:
    """Runtime registry for composite agent configuration objects."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._resource_roots: list[ResourceRoot] = discover_resource_roots(self._workspace_root)
        self._primary_resource_root = primary_resource_root(self._workspace_root, self._resource_roots)
        self._workspace_agents_dir: Path = self._primary_resource_root.path / "agents"
        self._legacy_workspace_agents_dir: Path = self._primary_resource_root.path / "agent-profiles"
        self._agents: Dict[str, Any] = {}
        self._flow_definitions: Dict[str, Any] = {}
        self._resource_root_filters = self._build_resource_root_filters()
        self._global_plugin_filter = DiscoveryFilter.from_root(
            self._workspace_root,
            ignore_dir=self._workspace_root,
        )

    def load(self, flow_definitions: Dict[str, Any]) -> None:
        """Rebuild the agent registry from flow definitions + workspace files."""
        from pocketcode.core.runtime_models import Agent  # noqa: PLC0415

        self._flow_definitions = {
            str(name): definition
            for name, definition in flow_definitions.items()
        }
        self._agents = {}
        self._resource_roots = discover_resource_roots(self._workspace_root)
        self._primary_resource_root = primary_resource_root(self._workspace_root, self._resource_roots)
        self._workspace_agents_dir = self._primary_resource_root.path / "agents"
        self._legacy_workspace_agents_dir = self._primary_resource_root.path / "agent-profiles"
        self._resource_root_filters = self._build_resource_root_filters()
        self._global_plugin_filter = DiscoveryFilter.from_root(
            self._workspace_root,
            ignore_dir=self._workspace_root,
        )

        for qname, defn in flow_definitions.items():
            explicit: Optional[Agent] = (
                getattr(defn, "default_agent", None)
                or getattr(defn, "default_agent_profile", None)
            )
            if explicit is not None:
                self._register(explicit, collision_source="plugin-declared")
                continue

            synth = Agent(
                name=qname,
                flow=qname,
                description=f"Synthesised default agent for {qname}.",
                llm_profile=getattr(defn, "llm_profile", None),
                extra_prompts=[],
                skills=None,
                tools=list(getattr(defn, "tools", None) or []) or None,
                tool_confirmation={},
                source="synthesised",
                source_path=None,
            )
            if synth.tools == []:
                synth.tools = None
            self._register(synth, collision_source="synthesised")

        self._load_plugin_files()
        self._load_workspace_files()

    def get(self, name: str) -> Optional[Any]:
        return self._agents.get(name)

    def list(self) -> List[Any]:
        return sorted(self._agents.values(), key=lambda agent: agent.name)

    def clone(self, src_name: str, new_name: str) -> Any:
        from pocketcode.core.runtime_models import Agent  # noqa: PLC0415
        import dataclasses  # noqa: PLC0415

        src: Optional[Agent] = self.get(src_name)
        if src is None:
            raise ValueError(
                f"Cannot clone: source agent '{src_name}' not found. "
                f"Available: {[p.name for p in self.list()]}"
            )

        target_path = self._workspace_agents_dir / f"{new_name}.yaml"
        if target_path.exists():
            raise ValueError(
                f"Cannot clone: target file '{target_path}' already exists. "
                "Choose a different name or remove the existing file first."
            )

        new_agent = dataclasses.replace(
            src,
            name=new_name,
            source="workspace",
            source_path=target_path,
        )
        self.save(new_agent)
        self.reload(self._flow_definitions)
        return self.get(new_name)

    def save(self, agent: Any) -> None:
        if agent.source_path is None:
            raise ValueError(
                f"Agent '{agent.name}' has no source_path; cannot save. "
                "Use clone() to promote an agent to a workspace file."
            )
        self._workspace_agents_dir.mkdir(parents=True, exist_ok=True)
        data = self._agent_to_yaml_dict(agent)
        agent.source_path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        logger.debug("Saved agent '%s' to %s", agent.name, agent.source_path)

    def delete(self, name: str) -> Path:
        agent = self.get(name)
        if agent is None:
            raise ValueError(f"Unknown agent profile '{name}'.")
        if agent.source != "workspace" or agent.source_path is None:
            raise ValueError(
                f"Agent profile '{name}' is not workspace-backed. Only workspace agents can be deleted."
            )
        target_path = Path(agent.source_path)
        if not target_path.exists():
            raise ValueError(f"Agent profile file does not exist: {target_path}")
        target_path.unlink()
        logger.debug("Deleted workspace agent '%s' from %s", name, target_path)
        self.reload(self._flow_definitions)
        return target_path

    def reload(self, flow_definitions: Dict[str, Any]) -> None:
        self.load(flow_definitions)

    def _register(self, agent: Any, collision_source: str) -> None:
        existing = self._agents.get(agent.name)
        if existing is not None:
            precedence = {"plugin": 3, "synthesised": 1, "workspace": 2}
            incoming_rank = precedence.get(agent.source, 0)
            existing_rank = precedence.get(existing.source, 0)

            logger.warning(
                "Agent name collision for '%s': existing source='%s', incoming source='%s' (%s). %s wins.",
                agent.name,
                existing.source,
                agent.source,
                collision_source,
                "Existing" if existing_rank >= incoming_rank else "Incoming",
            )
            if incoming_rank > existing_rank:
                self._agents[agent.name] = agent
            return

        self._agents[agent.name] = agent

    def _load_plugin_files(self) -> None:
        plugin_roots: set[Path] = set()
        for defn in self._flow_definitions.values():
            metadata = getattr(defn, "metadata", {}) or {}
            plugin_root = metadata.get("plugin_root")
            if isinstance(plugin_root, str) and plugin_root.strip():
                plugin_roots.add(Path(plugin_root).resolve())

        for plugin_root in sorted(plugin_roots):
            agents_dir = plugin_root / "agents"
            if not agents_dir.is_dir():
                continue
            for yaml_file in sorted(agents_dir.glob("*.yaml")):
                if self._plugin_agent_file_is_ignored(plugin_root, yaml_file):
                    continue
                self._load_agent_file(yaml_file, source="plugin")

    def _load_workspace_files(self) -> None:
        for resource_root in self._resource_roots:
            resource_filter = self._resource_root_filter(resource_root)
            yaml_files: List[Path] = []
            legacy_dir = resource_root.path / "agent-profiles"
            agents_dir = resource_root.path / "agents"
            if legacy_dir.exists():
                yaml_files.extend(sorted(legacy_dir.glob("*.yaml")))
            if agents_dir.exists():
                yaml_files.extend(sorted(agents_dir.glob("*.yaml")))

            for yaml_file in yaml_files:
                if resource_filter.ignores(yaml_file, is_dir=False):
                    continue
                self._load_agent_file(yaml_file, source="workspace")

    def _plugin_agent_file_is_ignored(self, plugin_root: Path, yaml_file: Path) -> bool:
        resolved_plugin_root = plugin_root.resolve()
        resolved_yaml = yaml_file.resolve()
        containing_root = resource_root_for_path(resolved_plugin_root, self._resource_roots)
        if containing_root is not None:
            return self._resource_root_filter(containing_root).ignores(resolved_yaml, is_dir=False)
        try:
            relative = resolved_yaml.relative_to(resolved_plugin_root)
        except ValueError:
            return False
        return self._global_plugin_filter.ignores_relative(
            Path(resolved_plugin_root.name) / relative,
            is_dir=False,
        )

    def _build_resource_root_filters(self) -> Dict[Path, DiscoveryFilter]:
        return {
            resource_root.path.resolve(): DiscoveryFilter.from_root(
                resource_root.path,
                ignore_dir=resource_root.path,
            )
            for resource_root in self._resource_roots
        }

    def _resource_root_filter(self, resource_root: ResourceRoot) -> DiscoveryFilter:
        return self._resource_root_filters[resource_root.path.resolve()]

    def _load_agent_file(self, yaml_file: Path, *, source: str) -> None:
        from pocketcode.core.runtime_models import Agent  # noqa: PLC0415
        try:
            raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                logger.warning(
                    "Skipping agent file '%s': root must be a YAML mapping.", yaml_file
                )
                return

            name = raw.get("name")
            flow_name = raw.get("flow") or raw.get("agent")
            if not name:
                logger.warning(
                    "Skipping agent file '%s': missing required field 'name'.", yaml_file
                )
                return
            if not flow_name:
                logger.warning(
                    "Skipping agent file '%s': missing required field 'flow'.", yaml_file
                )
                return

            normalized_flow_name = str(flow_name).strip()
            validate_registry_reference(
                normalized_flow_name,
                allowed_kinds={"agent", "flow"},
                field_name=f"{yaml_file.name}: flow",
            )
            normalized_flow_name = normalize_registry_reference(
                normalized_flow_name,
                allowed_kinds={"agent", "flow"},
            )
            flow_def = (
                self._flow_definitions.get(str(flow_name))
                or self._flow_definitions.get(normalized_flow_name)
            )

            tool_confirmation_raw = raw.get("tool_confirmation", {})
            if not isinstance(tool_confirmation_raw, dict):
                tool_confirmation_raw = {}

            has_tools_key = "tools" in raw
            tools_raw = raw.get("tools") if has_tools_key else None
            if tools_raw is not None and not isinstance(tools_raw, list):
                tools_raw = None
            has_skills_key = "skills" in raw
            skills_raw = raw.get("skills") if has_skills_key else None
            if skills_raw is not None and not isinstance(skills_raw, list):
                skills_raw = None

            inherited_tools = list(getattr(flow_def, "tools", None) or []) or None
            extra_prompts = [str(p) for p in raw.get("extra_prompts", []) if isinstance(p, str)]
            for index, prompt_ref in enumerate(extra_prompts):
                validate_prompt_source(prompt_ref, field_name=f"{yaml_file.name}: extra_prompts[{index}]")
            extra_prompts = [normalize_prompt_source(prompt_ref) for prompt_ref in extra_prompts]

            normalized_tools = None
            if has_tools_key and tools_raw is not None:
                normalized_tools = [str(t) for t in tools_raw if isinstance(t, str)]
                for index, tool_ref in enumerate(normalized_tools):
                    validate_registry_reference(
                        tool_ref,
                        allowed_kinds={"tool"},
                        field_name=f"{yaml_file.name}: tools[{index}]",
                    )
                normalized_tools = [
                    normalize_registry_reference(tool_ref, allowed_kinds={"tool"})
                    for tool_ref in normalized_tools
                ]

            agent = Agent(
                name=str(name),
                flow=normalized_flow_name,
                description=str(raw.get("description", "")),
                llm_profile=(
                    str(raw["llm_profile"])
                    if raw.get("llm_profile")
                    else getattr(flow_def, "llm_profile", None)
                ),
                extra_prompts=extra_prompts,
                skills=(
                    [str(skill) for skill in skills_raw if isinstance(skill, str)]
                    if has_skills_key and skills_raw is not None
                    else None
                ),
                tools=(
                    normalized_tools
                    if has_tools_key and normalized_tools is not None
                    else inherited_tools
                ),
                tool_confirmation={
                    "default": str(tool_confirmation_raw["default"])
                    if tool_confirmation_raw.get("default")
                    else None,
                    "overrides": {
                        str(k): str(v)
                        for k, v in (tool_confirmation_raw.get("overrides") or {}).items()
                        if isinstance(k, str) and isinstance(v, str)
                    },
                },
                source=source,
                source_path=yaml_file.resolve() if source == "workspace" else None,
            )
            self._register(agent, collision_source=str(yaml_file))
        except yaml.YAMLError as exc:
            logger.warning("Skipping agent file '%s': invalid YAML — %s", yaml_file, exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping agent file '%s': unexpected error — %s", yaml_file, exc)

    @staticmethod
    def _agent_to_yaml_dict(agent: Any) -> Dict[str, Any]:
        tool_confirmation: Dict[str, Any] = {}
        raw_tc = agent.tool_confirmation or {}
        default_policy = raw_tc.get("default")
        overrides = raw_tc.get("overrides") or {}
        if default_policy:
            tool_confirmation["default"] = default_policy
        if overrides:
            tool_confirmation["overrides"] = {
                normalize_registry_reference(str(tool_name), allowed_kinds={"tool"}): str(policy)
                for tool_name, policy in overrides.items()
                if str(tool_name).strip() and str(policy).strip()
            }

        data: Dict[str, Any] = {
            "name": agent.name,
            "flow": normalize_registry_reference(str(agent.flow), allowed_kinds={"agent", "flow"}),
        }
        if agent.description:
            data["description"] = agent.description
        if agent.llm_profile:
            data["llm_profile"] = agent.llm_profile
        if agent.skills is not None:
            data["skills"] = list(agent.skills)
        if agent.tools is not None:
            data["tools"] = [
                normalize_registry_reference(str(tool_name), allowed_kinds={"tool"})
                for tool_name in agent.tools
                if str(tool_name).strip()
            ]
        if agent.extra_prompts:
            data["extra_prompts"] = [
                normalize_prompt_source(str(prompt_ref))
                for prompt_ref in agent.extra_prompts
                if str(prompt_ref).strip()
            ]
        if tool_confirmation:
            data["tool_confirmation"] = tool_confirmation
        return data


AgentManager = CompositeAgentManager
AgentProfileManager = CompositeAgentManager
