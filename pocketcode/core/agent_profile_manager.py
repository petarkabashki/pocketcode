"""CompositeAgentManager — loads, indexes, and persists composite agent objects."""
from __future__ import annotations

import logging
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from pocketcode.core.discovery_rules import DiscoveryFilter
from pocketcode.core.catalog_metadata import namespace_name_from_metadata, namespace_root_from_metadata
from pocketcode.core.markdown_assets import (
    compile_markdown_agent_definition,
    load_markdown_asset_document,
    serialize_markdown_agent_definition,
)
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
WORKSPACE_NAMESPACE = "workspace"


def _normalize_agent_commands(raw_commands: Any, *, field_name: str) -> list[Any]:
    from pocketcode.core.runtime_models import AgentCommand  # noqa: PLC0415

    if raw_commands is None:
        return []
    if not isinstance(raw_commands, list):
        raise ValueError(f"{field_name}: commands must be a list when provided.")
    commands: list[AgentCommand] = []
    for index, raw in enumerate(raw_commands):
        if not isinstance(raw, dict):
            raise ValueError(f"{field_name}: commands[{index}] must be a mapping.")
        name = str(raw.get("name") or "").strip()
        if not name:
            raise ValueError(f"{field_name}: commands[{index}].name is required.")
        raw_target = raw.get("target")
        target_kind = "command"
        target = ""
        target_agent = None
        target_visibility = None
        target_handler = None
        if isinstance(raw_target, str):
            target = raw_target.strip()
            if not target:
                raise ValueError(f"{field_name}: commands[{index}].target is required.")
            try:
                shlex.split(target)
            except ValueError as exc:
                raise ValueError(f"{field_name}: commands[{index}].target is invalid: {exc}") from exc
        elif isinstance(raw_target, dict):
            target_kind = str(raw_target.get("kind") or "command").strip().lower() or "command"
            if target_kind == "command":
                target = str(raw_target.get("command") or raw_target.get("value") or "").strip()
                if not target:
                    raise ValueError(f"{field_name}: commands[{index}].target.command is required.")
                try:
                    shlex.split(target)
                except ValueError as exc:
                    raise ValueError(f"{field_name}: commands[{index}].target.command is invalid: {exc}") from exc
            elif target_kind == "agent_command":
                target_agent = str(raw_target.get("agent") or "").strip()
                target = str(raw_target.get("command") or "").strip()
                target_visibility = str(raw_target.get("visibility") or "").strip().lower() or None
                if not target_agent:
                    raise ValueError(f"{field_name}: commands[{index}].target.agent is required.")
                if not target:
                    raise ValueError(f"{field_name}: commands[{index}].target.command is required.")
                if target_visibility is not None and target_visibility not in {"private", "delegated", "exported"}:
                    raise ValueError(
                        f"{field_name}: commands[{index}].target.visibility must be one of private, delegated, exported."
                    )
            elif target_kind == "local_handler":
                target_handler = str(raw_target.get("handler") or "").strip()
                target = str(raw_target.get("command") or target_handler or "").strip()
                if not target_handler:
                    raise ValueError(f"{field_name}: commands[{index}].target.handler is required.")
            else:
                raise ValueError(
                    f"{field_name}: commands[{index}].target.kind must be 'command', 'agent_command', or 'local_handler'."
                )
        else:
            raise ValueError(f"{field_name}: commands[{index}].target must be a string or mapping.")
        visibility = str(raw.get("visibility") or "exported").strip().lower() or "exported"
        if visibility not in {"private", "delegated", "exported"}:
            raise ValueError(
                f"{field_name}: commands[{index}].visibility must be one of private, delegated, exported."
            )
        capabilities = [str(item).strip() for item in raw.get("capabilities", []) if str(item).strip()]
        payload_schema = dict(raw.get("payload_schema") or {}) if isinstance(raw.get("payload_schema"), dict) else {}
        result_schema = dict(raw.get("result_schema") or {}) if isinstance(raw.get("result_schema"), dict) else {}
        policy = dict(raw.get("policy") or {}) if isinstance(raw.get("policy"), dict) else {}
        commands.append(
            AgentCommand(
                name=name,
                target=target,
                target_kind=target_kind,
                target_agent=target_agent,
                target_visibility=target_visibility,
                target_handler=target_handler,
                visibility=visibility,
                description=str(raw.get("description") or "").strip(),
                capabilities=capabilities,
                payload_schema=payload_schema,
                result_schema=result_schema,
                policy=policy,
            )
        )
    return commands


class CompositeAgentManager:
    """Runtime registry for composite agent configuration objects."""

    def __init__(self, workspace_root: Path, *, prompt_registry: Any | None = None) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._prompt_registry = prompt_registry
        self._namespace_context_by_root: Dict[Path, str] = {}
        self._resource_roots: list[ResourceRoot] = discover_resource_roots(self._workspace_root)
        self._primary_resource_root = primary_resource_root(self._workspace_root, self._resource_roots)
        self._agents: Dict[str, Any] = {}
        self._resolved_agents: Dict[str, Any] = {}
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
        self._namespace_context_by_root = self._build_namespace_context_by_root(flow_definitions)
        self._agents = {}
        self._resolved_agents = {}
        self._resource_roots = discover_resource_roots(self._workspace_root)
        self._primary_resource_root = primary_resource_root(self._workspace_root, self._resource_roots)
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
                hooks=None,
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
        self._resolved_agents = self._resolve_all_agents()

    def get(self, name: str) -> Optional[Any]:
        return self._agents.get(name)

    def resolve(self, name: str) -> Optional[Any]:
        return self._resolved_agents.get(name)

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

        suffix = ".agent.yaml"
        if src.source_path is not None and Path(src.source_path).name.endswith(".agent.md"):
            suffix = ".agent.md"
        target_path = self._workspace_agent_path(new_name, suffix=suffix)
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
        target_path = Path(agent.source_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.suffix.lower() == ".md":
            agent.source_path.write_text(
                serialize_markdown_agent_definition(agent),
                encoding="utf-8",
            )
        else:
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
            precedence = {"namespace": 3, "synthesised": 1, "workspace": 2}
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
        plugin_roots: dict[Path, str | None] = {}
        for definition in self._flow_definitions.values():
            metadata = getattr(definition, "metadata", {}) or {}
            plugin_root_value = metadata.get("namespace_root")
            if not plugin_root_value:
                continue
            plugin_root = Path(str(plugin_root_value)).resolve()
            if not plugin_root.is_dir():
                continue
            plugin_roots.setdefault(plugin_root, self._plugin_context_for_root(plugin_root))

        for plugin_root in sorted(plugin_roots):
            for agent_file in [
                *sorted(plugin_root.glob("*.agent.yaml")),
                *sorted(plugin_root.glob("*.agent.md")),
            ]:
                if self._plugin_agent_file_is_ignored(plugin_root, agent_file):
                    continue
                self._load_agent_file(agent_file, source="namespace", plugin_root=plugin_root)

    def _load_workspace_files(self) -> None:
        for resource_root in self._resource_roots:
            resource_filter = self._resource_root_filter(resource_root)
            for yaml_file, default_name in self._iter_workspace_agent_files(resource_root):
                if resource_filter.ignores(yaml_file, is_dir=False):
                    continue
                self._load_agent_file(yaml_file, source="workspace", default_name=default_name)

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

    @staticmethod
    def _is_agent_profile_file(path: Path) -> bool:
        name = path.name.lower()
        return not name.endswith(".prompt.md")

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

    def _iter_workspace_agent_files(self, resource_root: ResourceRoot) -> list[tuple[Path, str | None]]:
        files: list[tuple[Path, str | None]] = []
        seen: set[Path] = set()

        for path in sorted(path for path in resource_root.path.glob("*.agent.yaml") if self._is_agent_profile_file(path)):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append((path, None))

        for path in sorted(resource_root.path.glob("*.agent.md")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append((path, None))

        agent_roots: list[tuple[Path, str | None]] = []
        agents_root = resource_root.path / "agents"
        if agents_root.is_dir():
            agent_roots.append((agents_root, None))
        for path in sorted(candidate for candidate in resource_root.path.iterdir() if candidate.is_dir()):
            if path.name.startswith("agent."):
                agent_roots.append((path, path.name[len("agent."):].strip() or None))

        for agent_root, prefix in agent_roots:
            for path in sorted(candidate for candidate in agent_root.rglob("*.agent.yaml") if candidate.is_file()):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                asset_name = self._workspace_asset_name(agent_root, path, suffix=".agent.yaml")
                files.append((path, self._prefix_asset_name(prefix, asset_name)))
            for path in sorted(candidate for candidate in agent_root.rglob("*.agent.md") if candidate.is_file()):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                asset_name = self._workspace_asset_name(agent_root, path, suffix=".agent.md")
                files.append((path, self._prefix_asset_name(prefix, asset_name)))

        return files

    def _workspace_asset_name(self, root: Path, asset_path: Path, *, suffix: str) -> str:
        relative = asset_path.resolve().relative_to(root.resolve())
        parts = list(relative.parts)
        if not parts:
            return ""
        filename = parts[-1]
        if not filename.endswith(suffix):
            return ""
        parts[-1] = filename[: -len(suffix)]
        return ".".join(part for part in parts if part)

    def _prefix_asset_name(self, prefix: str | None, asset_name: str) -> str:
        if not prefix:
            return asset_name
        if not asset_name:
            return prefix
        return f"{prefix}.{asset_name}"

    def _workspace_agent_path(self, agent_name: str, *, suffix: str) -> Path:
        normalized_name = str(agent_name or "").strip()
        if not normalized_name:
            raise ValueError("Agent name must not be empty.")
        if suffix not in {".agent.md", ".agent.yaml"}:
            raise ValueError(f"Unsupported agent profile suffix: {suffix}")

        parts = [part for part in normalized_name.split(".") if part]
        if not parts:
            raise ValueError("Agent name must not be empty.")

        group = parts[0]
        relative_parts = parts[1:] or [group]
        target_dir = self._primary_resource_root.path / f"agent.{group}"
        if len(relative_parts) > 1:
            target_dir = target_dir.joinpath(*relative_parts[:-1])
        return target_dir / f"{relative_parts[-1]}{suffix}"

    def _workspace_prompt_fallback_dirs(self) -> tuple[Path, ...]:
        fallback_dirs = [self._workspace_root]
        fallback_dirs.extend(resource_root.path for resource_root in self._resource_roots)
        return tuple(dict.fromkeys(fallback_dirs))

    def _plugin_prompt_fallback_dirs(self, plugin_root: Path) -> tuple[Path, ...]:
        resolved_root = Path(plugin_root).resolve()
        return (resolved_root, *self._workspace_prompt_fallback_dirs())

    def _build_namespace_context_by_root(self, flow_definitions: Dict[str, Any]) -> Dict[Path, str]:
        contexts: Dict[Path, str] = {}
        for qualified_name, definition in flow_definitions.items():
            metadata = getattr(definition, "metadata", {}) or {}
            namespace_root = namespace_root_from_metadata(metadata)
            if namespace_root is None:
                continue
            cleaned_name = namespace_name_from_metadata(
                metadata,
                fallback_qualified_name=str(qualified_name),
            )
            if cleaned_name:
                contexts[namespace_root] = cleaned_name
        return contexts

    def _plugin_context_for_root(self, plugin_root: Path | None) -> str | None:
        if plugin_root is None:
            return None
        return self._namespace_context_by_root.get(Path(plugin_root).resolve())

    def _load_agent_file(
        self,
        yaml_file: Path,
        *,
        source: str,
        plugin_root: Path | None = None,
        default_name: str | None = None,
    ) -> None:
        from pocketcode.core.runtime_models import Agent  # noqa: PLC0415
        try:
            if yaml_file.suffix.lower() == ".md":
                markdown_kwargs: Dict[str, Any] = {}
                if source == "workspace":
                    markdown_kwargs = {
                        "fallback_dirs": self._workspace_prompt_fallback_dirs(),
                        "prompt_registry": self._prompt_registry,
                        "context_plugin": WORKSPACE_NAMESPACE,
                    }
                elif self._prompt_registry is not None:
                    context_plugin = self._plugin_context_for_root(plugin_root)
                    markdown_kwargs = {
                        "fallback_dirs": self._plugin_prompt_fallback_dirs(plugin_root) if plugin_root is not None else (),
                        "prompt_registry": self._prompt_registry,
                        "context_plugin": context_plugin,
                    }
                document = load_markdown_asset_document(yaml_file, **markdown_kwargs)
                raw = compile_markdown_agent_definition(
                    document,
                    default_name=default_name or yaml_file.stem,
                )
            else:
                raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                logger.warning(
                    "Skipping agent file '%s': root must be a YAML mapping.", yaml_file
                )
                return

            name = raw.get("name")
            flow_name = raw.get("flow") or raw.get("agent")
            base_agent = raw.get("base_agent") or raw.get("extends")
            
            # Hybrid agent support: check for self-contained flow fields
            flow_fields = {
                "vm_source", "vm_entry", "vm_module", "vm_modules", 
                "vm_file", "vm_files", "module", "entry_fn"
            }
            is_self_contained = any(field in raw for field in flow_fields)
            
            if not name:
                logger.warning(
                    "Skipping agent file '%s': missing required field 'name'.", yaml_file
                )
                return
                
            if is_self_contained:
                # Compile a FlowDefinition from these fields
                if not flow_name:
                    flow_name = f"agents.{name}"
                
                # We need to register this flow in the flow registry.
                # Since we don't have direct access to WorkspaceCatalog's flow registry here,
                # we'll store it in self._flow_definitions so it can be picked up.
                # However, the registry is usually owned by WorkspaceCatalog.
                # For workspace agents, we might need a way to inject this.
                
                # Re-using logic from WorkspaceCatalog._load_workspace_markdown_flow
                execution_mode = str(
                    raw.get("execution_mode")
                    or ("vm" if any(raw.get(key) for key in ("vm_source", "vm_file", "vm_module", "vm_files", "vm_modules")) else "llm")
                ).strip() or "llm"
                
                from pocketcode.core.runtime_models import FlowDefinition  # noqa: PLC0415
                from pocketcode.core.prompt_loader import coerce_str_list  # noqa: PLC0415
                
                # For self-contained agents, the flow definition is embedded
                flow_def_obj = FlowDefinition(
                    name=flow_name,
                    description=str(raw.get("description", "")),
                    llm_profile=str(raw.get("llm_profile")) if raw.get("llm_profile") else None,
                    tools=coerce_str_list(raw.get("tools")),
                    handoff_agents=coerce_str_list(raw.get("handoff_agents")),
                    execution_mode=execution_mode,
                    deterministic_handler=str(raw.get("deterministic_handler") or raw.get("handler") or "").strip() or None,
                    composite_agents=coerce_str_list(raw.get("composite_agents")),
                    system_prompt=str(raw.get("inline_prompt") or raw.get("prompt") or "").strip(),
                    # For self-contained, we might not have external prompt files easily resolvable here 
                    # without more complex logic, but inline_prompt is usually enough.
                    module=str(raw["module"]).strip() if raw.get("module") else None,
                    entry_fn=str(raw["entry_fn"]).strip() if raw.get("entry_fn") else None,
                    vm_entry=str(raw["vm_entry"]).strip() if raw.get("vm_entry") else None,
                    vm_module=str(raw["vm_module"]).strip() if raw.get("vm_module") else None,
                    vm_modules=coerce_str_list(raw.get("vm_modules")),
                    vm_file=str(raw["vm_file"]).strip() if raw.get("vm_file") else None,
                    vm_files=coerce_str_list(raw.get("vm_files")),
                    vm_source=str(raw["vm_source"]).strip() if raw.get("vm_source") else None,
                    metadata={
                        "source": "self-contained-markdown",
                        "path": str(yaml_file.resolve()),
                    }
                )
                self._flow_definitions[flow_name] = flow_def_obj
                # Ensure the agent profile points to this flow
                raw["flow"] = flow_name

            if not flow_name and not base_agent and not is_self_contained:
                logger.warning(
                    "Skipping agent file '%s': missing required field 'flow' or 'extends'.", yaml_file
                )
                return

            normalized_flow_name = str(flow_name).strip() if flow_name else None
            normalized_base_agent = str(base_agent).strip() if base_agent else None
            if not is_self_contained:
                if normalized_flow_name:
                    validate_registry_reference(
                        normalized_flow_name,
                        allowed_kinds={"agent", "flow"},
                        field_name=f"{yaml_file.name}: flow",
                    )
                    normalized_flow_name = normalize_registry_reference(
                        normalized_flow_name,
                        allowed_kinds={"agent", "flow"},
                    )
                if normalized_base_agent:
                    validate_registry_reference(
                        normalized_base_agent,
                        allowed_kinds={"agent", "flow"},
                        field_name=f"{yaml_file.name}: extends",
                    )
                    normalized_base_agent = normalize_registry_reference(
                        normalized_base_agent,
                        allowed_kinds={"agent", "flow"},
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
            has_hooks_key = "hooks" in raw
            hooks_raw = raw.get("hooks") if has_hooks_key else None
            if hooks_raw is not None and not isinstance(hooks_raw, list):
                hooks_raw = None
            normalized_hooks = None
            if has_hooks_key and hooks_raw is not None:
                normalized_hooks = [str(hook_ref) for hook_ref in hooks_raw if isinstance(hook_ref, str)]
                for index, hook_ref in enumerate(normalized_hooks):
                    validate_registry_reference(
                        hook_ref,
                        allowed_kinds={"hook"},
                        field_name=f"{yaml_file.name}: hooks[{index}]",
                    )
                normalized_hooks = [
                    normalize_registry_reference(hook_ref, allowed_kinds={"hook"})
                    for hook_ref in normalized_hooks
                ]

            extra_prompts = [str(p) for p in raw.get("extra_prompts", []) if isinstance(p, str)]
            for index, prompt_ref in enumerate(extra_prompts):
                validate_prompt_source(prompt_ref, field_name=f"{yaml_file.name}: extra_prompts[{index}]")
            extra_prompts = [normalize_prompt_source(prompt_ref) for prompt_ref in extra_prompts]
            commands = _normalize_agent_commands(raw.get("commands"), field_name=yaml_file.name)

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
                flow=normalized_flow_name or "",
                base_agent=normalized_base_agent,
                description=str(raw.get("description", "")),
                llm_profile=str(raw["llm_profile"]) if raw.get("llm_profile") else None,
                extra_prompts=extra_prompts,
                hooks=normalized_hooks if has_hooks_key and normalized_hooks is not None else None,
                skills=(
                    [str(skill) for skill in skills_raw if isinstance(skill, str)]
                    if has_skills_key and skills_raw is not None
                    else None
                ),
                inline_prompt=str(raw.get("inline_prompt") or raw.get("prompt") or "").strip(),
                tools=normalized_tools if has_tools_key and normalized_tools is not None else None,
                commands=commands,
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
        }
        if getattr(agent, "base_agent", None):
            data["extends"] = normalize_registry_reference(str(agent.base_agent), allowed_kinds={"agent", "flow"})
        if getattr(agent, "flow", None):
            data["flow"] = normalize_registry_reference(str(agent.flow), allowed_kinds={"agent", "flow"})
        if agent.description:
            data["description"] = agent.description
        if agent.llm_profile:
            data["llm_profile"] = agent.llm_profile
        if agent.skills is not None:
            data["skills"] = list(agent.skills)
        if agent.hooks is not None:
            data["hooks"] = [
                normalize_registry_reference(str(hook_name), allowed_kinds={"hook"})
                for hook_name in agent.hooks
                if str(hook_name).strip()
            ]
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
        if getattr(agent, "commands", None):
            data["commands"] = [
                {
                    "name": str(command.name),
                    "target": (
                        str(command.target)
                        if str(getattr(command, "target_kind", "command") or "command").strip().lower() == "command"
                        else {
                            "kind": str(getattr(command, "target_kind", "command") or "command"),
                            "agent": str(getattr(command, "target_agent", "") or ""),
                            **(
                                {"handler": str(getattr(command, "target_handler", "") or "")}
                                if str(getattr(command, "target_handler", "") or "").strip()
                                else {}
                            ),
                            "command": str(getattr(command, "target", "") or ""),
                            **(
                                {"visibility": str(getattr(command, "target_visibility", "") or "")}
                                if str(getattr(command, "target_visibility", "") or "").strip()
                                else {}
                            ),
                        }
                    ),
                    **({"visibility": str(command.visibility)} if str(getattr(command, "visibility", "") or "").strip() else {}),
                    **({"description": str(command.description)} if str(getattr(command, "description", "") or "").strip() else {}),
                    **({"capabilities": list(command.capabilities)} if getattr(command, "capabilities", None) else {}),
                    **({"payload_schema": dict(command.payload_schema)} if getattr(command, "payload_schema", None) else {}),
                    **({"result_schema": dict(command.result_schema)} if getattr(command, "result_schema", None) else {}),
                    **({"policy": dict(command.policy)} if getattr(command, "policy", None) else {}),
                }
                for command in list(agent.commands)
                if str(getattr(command, "name", "") or "").strip() and str(getattr(command, "target", "") or "").strip()
            ]
        if tool_confirmation:
            data["tool_confirmation"] = tool_confirmation
        return data

    def _resolve_all_agents(self) -> Dict[str, Any]:
        resolved: Dict[str, Any] = {}
        failed: set[str] = set()
        for name in list(self._agents):
            materialized = self._resolve_agent(name, resolved=resolved, resolving=[], failed=failed)
            if materialized is not None:
                resolved[name] = materialized
        return resolved

    def _resolve_agent(
        self,
        name: str,
        *,
        resolved: Dict[str, Any],
        resolving: List[str],
        failed: set[str],
    ) -> Any | None:
        if name in resolved:
            return resolved[name]
        if name in failed:
            return None
        raw_agent = self._agents.get(name)
        if raw_agent is None:
            failed.add(name)
            return None
        if name in resolving:
            logger.warning("Skipping agent '%s': inheritance cycle detected (%s).", name, " -> ".join([*resolving, name]))
            failed.add(name)
            return None

        base_agent_name = str(getattr(raw_agent, "base_agent", "") or "").strip() or None
        base_agent = None
        if base_agent_name:
            base_agent = self._resolve_agent(
                base_agent_name,
                resolved=resolved,
                resolving=[*resolving, name],
                failed=failed,
            )
            if base_agent is None:
                logger.warning(
                    "Skipping agent '%s': extends unknown or invalid base agent '%s'.",
                    name,
                    base_agent_name,
                )
                failed.add(name)
                return None

        materialized = self._merge_agent(base_agent, raw_agent)
        if not str(getattr(materialized, "flow", "") or "").strip():
            logger.warning("Skipping agent '%s': no target flow after inheritance resolution.", name)
            failed.add(name)
            return None
        resolved[name] = materialized
        return materialized

    def _merge_agent(self, base_agent: Any | None, agent: Any) -> Any:
        from pocketcode.core.runtime_models import Agent  # noqa: PLC0415

        if base_agent is None:
            return Agent(
                name=agent.name,
                flow=agent.flow,
                base_agent=agent.base_agent,
                description=agent.description,
                llm_profile=agent.llm_profile,
                inline_prompt=agent.inline_prompt,
                extra_prompts=list(agent.extra_prompts),
                hooks=None if agent.hooks is None else list(agent.hooks),
                skills=None if agent.skills is None else list(agent.skills),
                tools=None if agent.tools is None else list(agent.tools),
                commands=list(agent.commands),
                tool_confirmation={
                    "default": (agent.tool_confirmation or {}).get("default"),
                    "overrides": dict((agent.tool_confirmation or {}).get("overrides") or {}),
                },
                source=agent.source,
                source_path=agent.source_path,
            )

        merged_prompt_parts = [part for part in [base_agent.inline_prompt, agent.inline_prompt] if str(part or "").strip()]
        merged_confirmation = {
            "default": (base_agent.tool_confirmation or {}).get("default"),
            "overrides": dict((base_agent.tool_confirmation or {}).get("overrides") or {}),
        }
        agent_confirmation = agent.tool_confirmation or {}
        if agent_confirmation.get("default") is not None:
            merged_confirmation["default"] = agent_confirmation.get("default")
        merged_confirmation["overrides"].update(dict(agent_confirmation.get("overrides") or {}))
        if not merged_confirmation["overrides"]:
            merged_confirmation.pop("overrides", None)
        if merged_confirmation.get("default") is None and "default" in merged_confirmation:
            merged_confirmation.pop("default", None)
        merged_commands: dict[str, Any] = {
            str(command.name): command
            for command in list(getattr(base_agent, "commands", []) or [])
            if str(getattr(command, "name", "") or "").strip()
        }
        for command in list(getattr(agent, "commands", []) or []):
            command_name = str(getattr(command, "name", "") or "").strip()
            if command_name:
                merged_commands[command_name] = command

        return Agent(
            name=agent.name,
            flow=agent.flow or base_agent.flow,
            base_agent=agent.base_agent,
            description=agent.description or base_agent.description,
            llm_profile=agent.llm_profile if agent.llm_profile is not None else base_agent.llm_profile,
            inline_prompt="\n\n".join(merged_prompt_parts),
            extra_prompts=[*list(base_agent.extra_prompts), *list(agent.extra_prompts)],
            hooks=list(agent.hooks) if agent.hooks is not None else (list(base_agent.hooks) if base_agent.hooks is not None else None),
            skills=list(agent.skills) if agent.skills is not None else (list(base_agent.skills) if base_agent.skills is not None else None),
            tools=list(agent.tools) if agent.tools is not None else (list(base_agent.tools) if base_agent.tools is not None else None),
            commands=list(merged_commands.values()),
            tool_confirmation=merged_confirmation,
            source=agent.source,
            source_path=agent.source_path,
        )


AgentManager = CompositeAgentManager
AgentProfileManager = CompositeAgentManager
