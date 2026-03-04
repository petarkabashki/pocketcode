from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

from pocketcode.core.prompt_loader import coerce_str_list, resolve_prompt_bundle
from pocketcode.core.runtime_models import (
    AgentDefinition,
    ComponentDefinition,
    CustomNodeHandlerDefinition,
    WorkflowDefinition,
)
from pocketcode.core.workflow_parser import parse_markdown_workflow

logger = logging.getLogger(__name__)


class PluginManager:
    def __init__(self, config: Dict[str, Any], workspace_root: str | Path):
        self._config = config
        self._workspace_root = Path(workspace_root).resolve()

        self.tools: Dict[str, Any] = {}
        self.components: Dict[str, ComponentDefinition] = {}
        self.agents: Dict[str, AgentDefinition] = {}
        self.workflows: Dict[str, WorkflowDefinition] = {}
        self.llm_profiles: Dict[str, Dict[str, Any]] = {}
        self.node_definitions: Dict[str, Dict[str, Any]] = {}
        self.node_handlers: Dict[str, CustomNodeHandlerDefinition] = {}
        self.plugin_roots: Dict[str, Path] = {}

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def clear(self) -> None:
        self.tools.clear()
        self.components.clear()
        self.agents.clear()
        self.workflows.clear()
        self.llm_profiles.clear()
        self.node_definitions.clear()
        self.node_handlers.clear()
        self.plugin_roots.clear()

    def load(self) -> None:
        self.clear()

        for plugin_root in self._iter_plugin_roots():
            try:
                self._load_plugin(plugin_root)
            except Exception as exc:
                logger.error("Failed loading plugin at %s: %s", plugin_root, exc, exc_info=True)

        logger.info(
            (
                "Plugin load complete. plugins=%s, tools=%s, agents=%s, workflows=%s, "
                "components=%s, node_definitions=%s, node_handlers=%s, llm_profiles=%s"
            ),
            len(self.plugin_roots),
            len(self.tools),
            len(self.agents),
            len(self.workflows),
            len(self.components),
            len(self.node_definitions),
            len(self.node_handlers),
            len(self.llm_profiles),
        )

    def resolve_tools_for_agent(self, agent_name: str) -> List[str]:
        agent = self.agents.get(agent_name)
        if not agent:
            return []

        if not agent.tools:
            return sorted(self.tools.keys())

        resolved: List[str] = []
        for tool_name in agent.tools:
            if tool_name == "*":
                return sorted(self.tools.keys())
            if tool_name in self.tools and tool_name not in resolved:
                resolved.append(tool_name)
                continue
            logger.warning("Agent '%s' references unknown tool '%s'.", agent_name, tool_name)

        return resolved

    def _iter_plugin_roots(self) -> Iterable[Path]:
        built_in_plugins_root = Path(__file__).resolve().parent.parent / "plugins"

        candidate_roots: List[Path] = [built_in_plugins_root]
        runtime_paths = (
            self._config.get("runtime", {}).get("plugin_paths", [])
            if isinstance(self._config, dict)
            else []
        )

        for raw_path in runtime_paths:
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            expanded = Path(raw_path).expanduser()
            if not expanded.is_absolute():
                expanded = (self._workspace_root / expanded).resolve()
            candidate_roots.append(expanded)

        seen: set[Path] = set()
        for base_path in candidate_roots:
            if not base_path.exists():
                continue

            if (base_path / "plugin.yaml").is_file():
                resolved = base_path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    yield resolved
                continue

            for child in sorted(base_path.iterdir()):
                if child.is_dir() and (child / "plugin.yaml").is_file():
                    resolved = child.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        yield resolved

    def _load_plugin(self, plugin_root: Path) -> None:
        manifest_path = plugin_root / "plugin.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(manifest, dict):
            raise ValueError(f"Plugin manifest must be a YAML object: {manifest_path}")

        plugin_name = str(manifest.get("name") or plugin_root.name)
        self.plugin_roots[plugin_name] = plugin_root

        logger.info("Loading plugin '%s' from %s", plugin_name, plugin_root)

        self._load_plugin_llm_profiles(plugin_name, manifest)
        self._load_plugin_tools(plugin_name, plugin_root, manifest)
        plugin_node_definitions = self._load_plugin_node_definitions(plugin_name, plugin_root, manifest)
        self._load_plugin_node_handlers(plugin_name, plugin_root, manifest)
        self._load_plugin_agents(plugin_name, plugin_root, manifest)
        self._load_plugin_workflows(
            plugin_name=plugin_name,
            plugin_root=plugin_root,
            manifest=manifest,
            plugin_node_definitions=plugin_node_definitions,
        )
        self._load_plugin_components(
            plugin_name=plugin_name,
            plugin_root=plugin_root,
            manifest=manifest,
            plugin_node_definitions=plugin_node_definitions,
        )

    def _register_component(
        self,
        *,
        name: str,
        kind: str,
        plugin_name: str,
        plugin_root: Path,
        definition: Dict[str, Any],
        source: str,
    ) -> None:
        existing = self.components.get(name)
        if existing:
            logger.warning(
                "Component '%s' (%s) is being overwritten by plugin '%s' via %s.",
                name,
                existing.kind,
                plugin_name,
                source,
            )
        self.components[name] = ComponentDefinition(
            name=name,
            kind=kind,
            plugin_name=plugin_name,
            plugin_root=plugin_root,
            config=dict(definition),
            metadata={"source": source},
        )

    def _load_plugin_llm_profiles(self, plugin_name: str, manifest: Dict[str, Any]) -> None:
        llm_profiles = manifest.get("llm_profiles", {})
        if not isinstance(llm_profiles, dict):
            logger.warning("Plugin '%s' llm_profiles is not a mapping. Skipping.", plugin_name)
            return

        for profile_name, profile_config in llm_profiles.items():
            if not isinstance(profile_config, dict):
                logger.warning(
                    "Plugin '%s' llm profile '%s' must be a mapping. Skipping.",
                    plugin_name,
                    profile_name,
                )
                continue
            self.llm_profiles[str(profile_name)] = dict(profile_config)

    def _load_plugin_tools(self, plugin_name: str, plugin_root: Path, manifest: Dict[str, Any]) -> None:
        tools_section = manifest.get("tools", {})
        if not isinstance(tools_section, dict):
            logger.warning("Plugin '%s' tools section is not a mapping. Skipping.", plugin_name)
            return

        for tool_name, reference in tools_section.items():
            try:
                loaded_tool = self._load_reference(reference, plugin_root)
                self.tools[str(tool_name)] = loaded_tool
            except Exception as exc:
                logger.error(
                    "Plugin '%s' failed to load tool '%s' from '%s': %s",
                    plugin_name,
                    tool_name,
                    reference,
                    exc,
                )

    def _load_plugin_node_definitions(
        self,
        plugin_name: str,
        plugin_root: Path,
        manifest: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        node_definitions_section = manifest.get("node_definitions")
        if node_definitions_section is None:
            node_definitions_section = manifest.get("nodes", {})

        if not isinstance(node_definitions_section, dict):
            logger.warning("Plugin '%s' node_definitions section is not a mapping. Skipping.", plugin_name)
            return {}

        loaded_for_plugin: Dict[str, Dict[str, Any]] = {}

        for node_definition_name, raw_definition in node_definitions_section.items():
            if not isinstance(raw_definition, dict):
                logger.warning(
                    "Plugin '%s' node definition '%s' must be a mapping. Skipping.",
                    plugin_name,
                    node_definition_name,
                )
                continue

            definition = dict(raw_definition)
            prompt_text, prompt_sources = resolve_prompt_bundle(
                definition,
                base_dir=plugin_root,
                inline_keys=("prompt", "system_prompt"),
                file_keys=("prompt_file", "system_prompt_file"),
                files_key="prompt_files",
                default_files=[f"prompts/nodes/{node_definition_name}.md"],
            )
            if prompt_text:
                definition["prompt"] = prompt_text
            if prompt_sources:
                definition["prompt_sources"] = prompt_sources

            pre_handlers = list(
                dict.fromkeys(
                    coerce_str_list(definition.get("pre")) + coerce_str_list(definition.get("pre_steps"))
                )
            )
            step_handlers = list(
                dict.fromkeys(
                    coerce_str_list(definition.get("steps"))
                    + coerce_str_list(definition.get("exec"))
                    + coerce_str_list(definition.get("exec_steps"))
                )
            )
            post_handlers = list(
                dict.fromkeys(
                    coerce_str_list(definition.get("post")) + coerce_str_list(definition.get("post_steps"))
                )
            )
            if pre_handlers:
                definition["pre"] = pre_handlers
            if step_handlers:
                definition["steps"] = step_handlers
            if post_handlers:
                definition["post"] = post_handlers

            key = str(node_definition_name)
            loaded_for_plugin[key] = definition

            global_key = f"{plugin_name}.{key}"
            if global_key in self.node_definitions:
                logger.warning(
                    "Node definition '%s' is being overwritten by plugin '%s'.",
                    global_key,
                    plugin_name,
                )
            self.node_definitions[global_key] = definition

        return loaded_for_plugin

    def _load_plugin_node_handlers(self, plugin_name: str, plugin_root: Path, manifest: Dict[str, Any]) -> None:
        handlers_section = manifest.get("node_handlers", {})
        if not isinstance(handlers_section, dict):
            logger.warning("Plugin '%s' node_handlers section is not a mapping. Skipping.", plugin_name)
            return

        for kind_name, reference in handlers_section.items():
            kind = str(kind_name).strip().lower()
            if not kind:
                continue

            try:
                handler = self._load_reference(reference, plugin_root)
            except Exception as exc:
                logger.error(
                    "Plugin '%s' failed to load node handler '%s' from '%s': %s",
                    plugin_name,
                    kind,
                    reference,
                    exc,
                )
                continue

            if not callable(handler):
                logger.error(
                    "Plugin '%s' node handler '%s' is not callable: %s",
                    plugin_name,
                    kind,
                    type(handler),
                )
                continue

            if kind in self.node_handlers:
                logger.warning(
                    "Node handler kind '%s' is being overwritten by plugin '%s'.",
                    kind,
                    plugin_name,
                )

            self.node_handlers[kind] = CustomNodeHandlerDefinition(
                kind=kind,
                handler=handler,
                plugin_name=plugin_name,
                metadata={"reference": str(reference)},
            )

    def _load_plugin_agents(self, plugin_name: str, plugin_root: Path, manifest: Dict[str, Any]) -> None:
        agents_section = manifest.get("agents", {})
        if not isinstance(agents_section, dict):
            logger.warning("Plugin '%s' agents section is not a mapping. Skipping.", plugin_name)
            return

        for agent_name, raw_definition in agents_section.items():
            definition = raw_definition if isinstance(raw_definition, dict) else {}
            self._register_component(
                name=str(agent_name),
                kind="agent",
                plugin_name=plugin_name,
                plugin_root=plugin_root,
                definition=definition,
                source="legacy_agents",
            )
            self._register_agent_definition(
                agent_name=str(agent_name),
                definition=definition,
                plugin_name=plugin_name,
                plugin_root=plugin_root,
            )

    def _register_agent_definition(
        self,
        agent_name: str,
        definition: Dict[str, Any],
        plugin_name: str,
        plugin_root: Path,
    ) -> None:
        llm_profile = definition.get("llm_profile")
        tools = definition.get("tools", [])
        if not tools and definition.get("allowed_tools"):
            tools = definition.get("allowed_tools", [])
        handoff_agents = definition.get("handoff_agents", [])

        if not isinstance(tools, list):
            tools = []
        if not isinstance(handoff_agents, list):
            handoff_agents = []

        if definition.get("tool_packs"):
            logger.warning(
                "Plugin '%s' agent '%s' uses deprecated 'tool_packs'. Please migrate to 'tools'.",
                plugin_name,
                agent_name,
            )

        system_prompt, prompt_sources = resolve_prompt_bundle(
            definition,
            base_dir=plugin_root,
            inline_keys=("system_prompt", "prompt"),
            file_keys=("system_prompt_file", "prompt_file"),
            files_key="prompt_files",
            default_files=[f"prompts/agents/{agent_name}.md"],
        )

        self.agents[agent_name] = AgentDefinition(
            name=agent_name,
            description=str(definition.get("description", "")),
            llm_profile=str(llm_profile) if llm_profile else None,
            tools=[str(item) for item in tools if isinstance(item, str)],
            handoff_agents=[str(item) for item in handoff_agents if isinstance(item, str)],
            system_prompt=system_prompt,
            prompt_sources=prompt_sources,
            metadata={
                "plugin": plugin_name,
                "plugin_root": str(plugin_root),
            },
        )

    def _load_plugin_workflows(
        self,
        plugin_name: str,
        plugin_root: Path,
        manifest: Dict[str, Any],
        plugin_node_definitions: Dict[str, Dict[str, Any]],
    ) -> None:
        workflows_section = manifest.get("flows")
        if workflows_section is None:
            workflows_section = manifest.get("workflows", {})
        if not isinstance(workflows_section, dict):
            logger.warning("Plugin '%s' workflows section is not a mapping. Skipping.", plugin_name)
            return

        for workflow_name, workflow_entry in workflows_section.items():
            try:
                definition_for_component = (
                    workflow_entry if isinstance(workflow_entry, dict) else {"path": workflow_entry}
                )
                self._register_component(
                    name=str(workflow_name),
                    kind="workflow",
                    plugin_name=plugin_name,
                    plugin_root=plugin_root,
                    definition=definition_for_component,
                    source="legacy_workflows",
                )
                workflow_definition = self._load_workflow_definition(
                    workflow_name=str(workflow_name),
                    workflow_entry=workflow_entry,
                    plugin_name=plugin_name,
                    plugin_root=plugin_root,
                    plugin_node_definitions=plugin_node_definitions,
                )
                self.workflows[str(workflow_name)] = workflow_definition
            except Exception as exc:
                logger.error(
                    "Plugin '%s' failed to parse workflow '%s' (%s): %s",
                    plugin_name,
                    workflow_name,
                    workflow_entry,
                    exc,
                )

    def _load_plugin_components(
        self,
        plugin_name: str,
        plugin_root: Path,
        manifest: Dict[str, Any],
        plugin_node_definitions: Dict[str, Dict[str, Any]],
    ) -> None:
        components_section = manifest.get("components", {})
        if not isinstance(components_section, dict):
            logger.warning("Plugin '%s' components section is not a mapping. Skipping.", plugin_name)
            return

        for component_name, raw_definition in components_section.items():
            if not isinstance(raw_definition, dict):
                logger.warning(
                    "Plugin '%s' component '%s' must be a mapping. Skipping.",
                    plugin_name,
                    component_name,
                )
                continue

            definition = dict(raw_definition)
            kind = str(definition.get("kind", "")).strip().lower()
            if not kind:
                kind = self._infer_component_kind(definition)

            name = str(component_name)
            self._register_component(
                name=name,
                kind=kind,
                plugin_name=plugin_name,
                plugin_root=plugin_root,
                definition=definition,
                source="components",
            )

            try:
                if kind in {"agent", "llm", "assistant"}:
                    self._register_agent_definition(
                        agent_name=name,
                        definition=definition,
                        plugin_name=plugin_name,
                        plugin_root=plugin_root,
                    )
                    continue

                if kind in {"workflow", "flow", "graph", "composite", "custom_flow"}:
                    workflow_entry = (
                        definition.get("workflow")
                        or definition.get("path")
                        or definition.get("graph")
                        or definition.get("ref")
                        or definition.get("factory")
                        or definition.get("handler")
                        or definition.get("flow")
                        or definition
                    )
                    workflow_definition = self._load_workflow_definition(
                        workflow_name=name,
                        workflow_entry=workflow_entry,
                        plugin_name=plugin_name,
                        plugin_root=plugin_root,
                        plugin_node_definitions=plugin_node_definitions,
                    )
                    if isinstance(definition, dict):
                        workflow_definition = self._apply_workflow_metadata_overrides(
                            definition=workflow_definition,
                            metadata=definition,
                            plugin_root=plugin_root,
                        )
                    self.workflows[name] = workflow_definition
                    continue

                logger.warning(
                    "Plugin '%s' component '%s' has unsupported kind '%s'.",
                    plugin_name,
                    component_name,
                    kind,
                )
            except Exception as exc:
                logger.error(
                    "Plugin '%s' failed to materialize component '%s' (%s): %s",
                    plugin_name,
                    component_name,
                    kind,
                    exc,
                )

    def _infer_component_kind(self, definition: Dict[str, Any]) -> str:
        if any(key in definition for key in {"llm_profile", "tools", "allowed_tools", "handoff_agents"}):
            return "agent"
        if any(
            key in definition
            for key in {"workflow", "path", "graph", "ref", "factory", "handler", "flow", "markdown"}
        ):
            return "workflow"
        return "agent"

    def _load_workflow_definition(
        self,
        workflow_name: str,
        workflow_entry: Any,
        plugin_name: str,
        plugin_root: Path,
        plugin_node_definitions: Dict[str, Dict[str, Any]],
    ) -> WorkflowDefinition:
        if isinstance(workflow_entry, str):
            candidate_path = (plugin_root / workflow_entry).resolve()
            if candidate_path.is_file() and candidate_path.suffix.lower() in {".md", ".markdown"}:
                return parse_markdown_workflow(
                    workflow_path=candidate_path,
                    workflow_name=workflow_name,
                    plugin_name=plugin_name,
                    plugin_root=plugin_root,
                    plugin_node_definitions=plugin_node_definitions,
                )
            if workflow_entry.lower().endswith((".md", ".markdown")):
                raise FileNotFoundError(
                    f"Workflow markdown file not found for '{workflow_name}': {candidate_path}"
                )
            return self._build_custom_workflow_definition(
                workflow_name=workflow_name,
                plugin_name=plugin_name,
                plugin_root=plugin_root,
                flow_reference=workflow_entry,
                raw_metadata={},
            )

        if isinstance(workflow_entry, dict):
            markdown_path = (
                workflow_entry.get("path")
                or workflow_entry.get("workflow")
                or workflow_entry.get("markdown")
                or workflow_entry.get("graph")
            )
            if markdown_path:
                candidate_path = (plugin_root / str(markdown_path)).resolve()
                definition = parse_markdown_workflow(
                    workflow_path=candidate_path,
                    workflow_name=workflow_name,
                    plugin_name=plugin_name,
                    plugin_root=plugin_root,
                    plugin_node_definitions=plugin_node_definitions,
                )
                return self._apply_workflow_metadata_overrides(
                    definition=definition,
                    metadata=workflow_entry,
                    plugin_root=plugin_root,
                )

            flow_reference = (
                workflow_entry.get("ref")
                or workflow_entry.get("factory")
                or workflow_entry.get("handler")
                or workflow_entry.get("callable")
                or workflow_entry.get("flow")
            )
            if not flow_reference:
                raise ValueError(
                    f"Workflow '{workflow_name}' must include a markdown path or custom flow reference."
                )
            return self._build_custom_workflow_definition(
                workflow_name=workflow_name,
                plugin_name=plugin_name,
                plugin_root=plugin_root,
                flow_reference=str(flow_reference),
                raw_metadata=workflow_entry,
            )

        raise ValueError(
            f"Workflow '{workflow_name}' configuration must be a string or mapping, got {type(workflow_entry)}."
        )

    def _apply_workflow_metadata_overrides(
        self,
        definition: WorkflowDefinition,
        metadata: Dict[str, Any],
        plugin_root: Path,
    ) -> WorkflowDefinition:
        updated = definition
        if metadata.get("description"):
            updated.description = str(metadata["description"])
        if metadata.get("default_agent"):
            updated.default_agent = str(metadata["default_agent"])

        prompt_text, prompt_sources = resolve_prompt_bundle(
            metadata,
            base_dir=plugin_root,
            inline_keys=("prompt",),
            file_keys=("prompt_file",),
            files_key="prompt_files",
            default_files=[],
        )
        if prompt_text:
            updated.prompt = prompt_text
            updated.prompt_sources = prompt_sources

        pre_handlers = list(
            dict.fromkeys(
                coerce_str_list(metadata.get("pre")) + coerce_str_list(metadata.get("pre_steps"))
            )
        )
        step_handlers = list(
            dict.fromkeys(
                coerce_str_list(metadata.get("steps"))
                + coerce_str_list(metadata.get("exec"))
                + coerce_str_list(metadata.get("exec_steps"))
            )
        )
        post_handlers = list(
            dict.fromkeys(
                coerce_str_list(metadata.get("post")) + coerce_str_list(metadata.get("post_steps"))
            )
        )

        if pre_handlers:
            updated.pre_handlers = pre_handlers
        if step_handlers:
            updated.step_handlers = step_handlers
        if post_handlers:
            updated.post_handlers = post_handlers

        merged_metadata = dict(updated.metadata)
        merged_metadata.update(dict(metadata))
        updated.metadata = merged_metadata
        return updated

    def _build_custom_workflow_definition(
        self,
        workflow_name: str,
        plugin_name: str,
        plugin_root: Path,
        flow_reference: str,
        raw_metadata: Dict[str, Any],
    ) -> WorkflowDefinition:
        custom_flow = self._load_reference(flow_reference, plugin_root)
        if not callable(custom_flow) and not hasattr(custom_flow, "run"):
            raise TypeError(
                f"Custom flow reference '{flow_reference}' must be callable or have a run(shared_store) method."
            )

        prompt_text, prompt_sources = resolve_prompt_bundle(
            raw_metadata,
            base_dir=plugin_root,
            inline_keys=("prompt",),
            file_keys=("prompt_file",),
            files_key="prompt_files",
            default_files=[f"prompts/flows/{workflow_name}.md"],
        )
        pre_handlers = list(
            dict.fromkeys(
                coerce_str_list(raw_metadata.get("pre")) + coerce_str_list(raw_metadata.get("pre_steps"))
            )
        )
        step_handlers = list(
            dict.fromkeys(
                coerce_str_list(raw_metadata.get("steps"))
                + coerce_str_list(raw_metadata.get("exec"))
                + coerce_str_list(raw_metadata.get("exec_steps"))
            )
        )
        post_handlers = list(
            dict.fromkeys(
                coerce_str_list(raw_metadata.get("post")) + coerce_str_list(raw_metadata.get("post_steps"))
            )
        )

        default_agent = raw_metadata.get("default_agent")
        start_node = str(raw_metadata.get("start_node") or "__custom_flow__")

        return WorkflowDefinition(
            name=workflow_name,
            description=str(raw_metadata.get("description", "")),
            plugin_name=plugin_name,
            plugin_root=plugin_root,
            markdown_path=plugin_root / "<custom-flow>",
            start_node=start_node,
            default_agent=str(default_agent) if default_agent else None,
            workflow_kind="custom",
            custom_flow=custom_flow,
            prompt=prompt_text,
            prompt_sources=prompt_sources,
            pre_handlers=pre_handlers,
            step_handlers=step_handlers,
            post_handlers=post_handlers,
            metadata={**dict(raw_metadata), "reference": flow_reference},
        )

    def _load_reference(self, reference: Any, plugin_root: Path) -> Any:
        if not isinstance(reference, str):
            return reference

        candidate = reference.strip()
        if not candidate:
            raise ValueError("Empty reference string.")

        if ":" in candidate:
            path_part, object_name = candidate.split(":", 1)
            file_path = (plugin_root / path_part).resolve()
            if file_path.is_file():
                return self._load_from_file(file_path, object_name)

        if "." not in candidate:
            raise ValueError(
                f"Reference '{reference}' must be an import path (module.Object) or file reference (path.py:Object)."
            )

        module_name, object_name = candidate.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, object_name)

    def _load_from_file(self, file_path: Path, object_name: str) -> Any:
        module_name = f"pocketcode_dynamic_plugin_{abs(hash(str(file_path)))}"

        if module_name in sys.modules:
            module = sys.modules[module_name]
        else:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if not spec or not spec.loader:
                raise ImportError(f"Unable to create import spec for {file_path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

        return getattr(module, object_name)
