from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import sys
import types
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

from pocketcode.core.interfaces import BaseTool, Plugin, PluginContext
from pocketcode.core.manifest_loader import load_manifest
from pocketcode.core.namespace_registry import NamespaceRegistry, RegistryError, RegistryHolder
from pocketcode.core.prompt_loader import (
    coerce_str_list,
    is_prompt_reference,
    resolve_prompt_bundle,
    resolve_prompt_reference,
)
from pocketcode.core.discovery_rules import DiscoveryFilter
from pocketcode.core.markdown_assets import (
    build_markdown_tool_wrapper,
    compile_markdown_flow_definition,
    compile_markdown_tool_definition,
    load_markdown_asset_document,
)
from pocketcode.core.markdown_graph_flow import build_graph_flow_from_metadata
from pocketcode.core.resource_roots import (
    ResourceRoot,
    discover_resource_roots,
    is_default_resource_root,
    primary_resource_root,
    resource_root_for_path,
    resource_root_namespace,
)
from pocketcode.core.runtime_models import Agent, FlowDefinition

logger = logging.getLogger(__name__)

WORKSPACE_NAMESPACE = "workspace"


class PluginManager:
    def __init__(self, config: Dict[str, Any], workspace_root: str | Path):
        self._config = config
        self._workspace_root = Path(workspace_root).resolve()
        self._resource_roots: list[ResourceRoot] = discover_resource_roots(self._workspace_root)
        self._primary_resource_root = primary_resource_root(self._workspace_root, self._resource_roots)

        self.tools: NamespaceRegistry[Any] = NamespaceRegistry()
        self.flows: NamespaceRegistry[FlowDefinition] = NamespaceRegistry()
        self.agents = self.flows
        self.prompts: NamespaceRegistry[str] = NamespaceRegistry()
        self.llm_profiles: Dict[str, Dict[str, Any]] = {}
        self.plugin_roots: Dict[str, Path] = {}
        self.plugins: Dict[str, Plugin] = {}
        self._holder: RegistryHolder = RegistryHolder()
        self._dynamic_module_names: set[str] = set()
        self._resource_root_filters: Dict[Path, DiscoveryFilter] = self._build_resource_root_filters()
        self._global_plugin_filter = DiscoveryFilter.from_root(
            self._workspace_root,
            ignore_dir=self._workspace_root,
        )

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    @property
    def resource_roots(self) -> list[ResourceRoot]:
        return list(self._resource_roots)

    def clear(self) -> None:
        self._unload_dynamic_modules()
        self.tools = NamespaceRegistry()
        self.flows = NamespaceRegistry()
        self.agents = self.flows
        self.prompts = NamespaceRegistry()
        self.llm_profiles.clear()
        self.plugin_roots.clear()
        self.plugins.clear()
        self._resource_roots = discover_resource_roots(self._workspace_root)
        self._primary_resource_root = primary_resource_root(self._workspace_root, self._resource_roots)
        self._resource_root_filters = self._build_resource_root_filters()
        self._global_plugin_filter = DiscoveryFilter.from_root(
            self._workspace_root,
            ignore_dir=self._workspace_root,
        )

    def load(self) -> None:
        self.clear()

        self._load_workspace_prompts_only()

        for plugin_root in self._iter_plugin_roots():
            try:
                # Priority 1: factory-based get_plugin() - ALWAYS takes precedence
                # Check for __init__.py FIRST to handle factory-based plugins that might also have an agent.yaml
                if (plugin_root / "__init__.py").is_file():
                    loaded_factory = self._load_factory_plugin(plugin_root)
                    if loaded_factory:
                        continue
                
                # Priority 2: agent.yaml or plugin.yaml
                self._load_plugin(plugin_root)
            except Exception as exc:
                logger.error("Failed loading plugin at %s: %s", plugin_root, exc, exc_info=True)

        self._load_workspace_tools_only()
        self._load_workspace_flows_only()
        self._validate_loaded_flow_references()

        logger.info(
            "Plugin load complete. plugins=%d, tools=%d, flows=%d, llm_profiles=%d",
            len(self.plugin_roots),
            len(self.tools),
            len(self.flows),
            len(self.llm_profiles),
        )
        # Atomic registry swap — new sessions immediately see fresh state
        self._holder.swap(self)

    def _load_factory_plugin(self, plugin_root: Path) -> bool:
        """Attempts to load a plugin using the get_plugin(config) factory function."""
        init_path = plugin_root / "__init__.py"
        try:
            # We need to treat plugin_root as a module if it's within a package
            # Let's use _load_from_file to get the module and check for get_plugin
            module = self._load_module_from_file(init_path)
            factory = getattr(module, "get_plugin", None)
            
            if not factory or not callable(factory):
                logger.debug(f"No get_plugin(config) found in {init_path}")
                return False
                
            plugin_config = self._config.get("plugins", {}).get(plugin_root.name, {})
            plugin: Plugin = factory(plugin_config)
            
            if not isinstance(plugin, Plugin):
                logger.warning(f"Plugin factory at {plugin_root} returned {type(plugin)}, expected Plugin instance.")
                return False
                
            plugin_name = plugin.name or plugin_root.name
            self.plugin_roots[plugin_name] = plugin_root
            self.plugins[plugin_name] = plugin
            
            logger.info("Loading factory plugin '%s' from %s", plugin_name, plugin_root)
            
            # Register tools
            for tool in plugin.tools:
                tool_name = getattr(tool, "__name__", str(tool))
                try:
                    self.tools.register(plugin_name, tool_name, tool)
                except RegistryError:
                    logger.warning(
                        "Plugin '%s' tool '%s' collides with existing registration. Skipping.",
                        plugin_name,
                        tool_name,
                    )
            
            # Register flows
            for flow_name, flow in plugin.agents.items():
                flow_def = FlowDefinition(
                    name=flow_name,
                    description=plugin.description or f"Programmatic flow from {plugin_name}",
                    is_programmatic=True,
                    flow_instance=flow,
                    metadata={
                        "plugin": plugin_name,
                        "plugin_name": plugin_name,
                        "plugin_root": str(plugin_root),
                        "version": plugin.version,
                        "author": plugin.author,
                    },
                )
                try:
                    self.flows.register(plugin_name, flow_name, flow_def)
                except RegistryError:
                    logger.error(
                        "Plugin '%s' flow '%s' collides with existing registration. Skipping.",
                        plugin_name,
                        flow_name,
                    )
                
            # Register LLM profiles from metadata if present
            if "llm_profiles" in plugin.metadata:
                self._load_plugin_llm_profiles(plugin_name, plugin.metadata.get("llm_profiles", {}))
            self._load_factory_plugin_prompts(plugin_name, plugin)
                
            return True
            
        except Exception as exc:
            logger.error(f"Factory load failed for {plugin_root}: {exc}", exc_info=True)
            return False

    def _load_module_from_file(self, file_path: Path) -> Any:
        module_name = self._build_dynamic_module_name(file_path)
        sys.modules.pop(module_name, None)
        return self._execute_module_from_file(file_path, module_name)

    def resolve_tools_for_agent(self, agent_name: str) -> List[str]:
        try:
            normalized_agent_name = self.flows.qualify(agent_name)
        except RegistryError:
            return []

        agent = self.flows.get(normalized_agent_name)
        if not agent:
            return []

        context_plugin = (agent.metadata or {}).get("plugin")

        if not agent.tools:
            return self.tools.list_all()  # all qualified names

        resolved: List[str] = []
        for tool_ref in agent.tools:
            if tool_ref == "*":
                return self.tools.list_all()

            tool_ref = self.tools._normalize_ref(tool_ref)

            # Determine the qualified name for this tool reference
            if "." in tool_ref:
                if tool_ref not in self.tools:
                    logger.warning("Agent '%s' references unknown tool '%s'.", normalized_agent_name, tool_ref)
                    continue
                qname = tool_ref
            elif context_plugin and self.tools.has_local(context_plugin, tool_ref):
                qname = f"{context_plugin}.{tool_ref}"  # local plugin owns it
            else:
                owners = self.tools.owners_for(tool_ref)
                if not owners:
                    logger.warning("Agent '%s' references unknown tool '%s'.", normalized_agent_name, tool_ref)
                    continue
                qname = owners[0]
                if len(owners) > 1:
                    logger.warning(
                        "Ambiguous tool '%s' for agent '%s': owned by %s. Using '%s'.",
                        tool_ref,
                        normalized_agent_name,
                        ", ".join(f"'{o}'" for o in owners),
                        qname,
                    )

            if qname not in resolved:
                resolved.append(qname)

        return resolved

    def resolve_tools_for_flow(self, flow_name: str) -> List[str]:
        """Canonical name for resolving tools from a registered flow."""
        return self.resolve_tools_for_agent(flow_name)

    def _iter_plugin_roots(self) -> Iterable[Path]:
        built_in_plugins_root = Path(__file__).resolve().parent.parent / "plugins"

        candidate_roots: List[Path] = [built_in_plugins_root]
        for resource_root in self._resource_roots:
            candidate_roots.append(resource_root.path / "plugins")
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

            # Check if current base_path itself is a plugin (has __init__.py, agent.yaml, or plugin.yaml)
            if (base_path / "__init__.py").is_file() or (base_path / "agent.yaml").is_file() or (base_path / "plugin.yaml").is_file():
                resolved = base_path.resolve()
                if resolved not in seen and not self._plugin_root_is_ignored(resolved):
                    seen.add(resolved)
                    yield resolved
                continue

            # Otherwise, iterate through children
            for child in sorted(base_path.iterdir()):
                if (
                    child.is_dir()
                    and not self._plugin_root_is_ignored(child)
                    and (
                        (child / "__init__.py").is_file()
                        or (child / "agent.yaml").is_file()
                        or (child / "plugin.yaml").is_file()
                    )
                ):
                    resolved = child.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        yield resolved

    def _load_plugin(self, plugin_root: Path) -> None:
        if (plugin_root / "agent.yaml").is_file():
            load_manifest(plugin_root / "agent.yaml")
            self._load_agent_plugin(plugin_root)
            return

        manifest_path = plugin_root / "plugin.yaml"
        manifest = load_manifest(manifest_path)
        plugin_name = manifest.name
        self.plugin_roots[plugin_name] = plugin_root

        logger.info("Loading manifest plugin '%s' from %s", plugin_name, plugin_root)

        self._load_plugin_llm_profiles(plugin_name, manifest.llm_profiles)
        self._load_plugin_prompts(plugin_name, plugin_root, manifest.prompts)
        self._load_plugin_tools(plugin_name, plugin_root, manifest.tools)
        self._load_plugin_flows(plugin_name, plugin_root, manifest.flows)

        # Explicitly ignore removed legacy sections.
        raw_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if isinstance(raw_manifest, dict):
            for legacy_key in ("components", "workflows", "modes"):
                if legacy_key in raw_manifest:
                    logger.warning(
                        "Plugin '%s' contains legacy '%s' section; it is ignored in agent-only runtime.",
                        plugin_name,
                        legacy_key,
                    )

    def _load_workspace_prompts_only(self) -> None:
        for resource_root in self._resource_roots:
            self._load_workspace_prompts(resource_root, resource_root.path / "prompts")

    def _load_workspace_tools_only(self) -> None:
        for resource_root in self._resource_roots:
            self._load_workspace_tools(resource_root, resource_root.path / "tools")

    def _load_workspace_flows_only(self) -> None:
        for resource_root in self._resource_roots:
            self._load_workspace_flows(resource_root, resource_root.path / "flows")

    def _load_workspace_prompts(self, resource_root: ResourceRoot, prompts_root: Path) -> None:
        if not prompts_root.is_dir():
            return

        for prompt_path in sorted(path for path in prompts_root.rglob("*") if path.is_file()):
            resource_filter = self._resource_root_filter(resource_root)
            if resource_filter.ignores(prompt_path, is_dir=False):
                continue
            prompt_name = self._workspace_resource_name(prompts_root, prompt_path)
            if not prompt_name:
                continue
            prompt_text = prompt_path.read_text(encoding="utf-8")
            for namespace in self._resource_root_namespaces(resource_root):
                try:
                    self.prompts.register(namespace, prompt_name, prompt_text)
                except RegistryError as exc:
                    logger.warning(
                        "Resource-root prompt '%s' at '%s' collides with an existing registration in '%s': %s",
                        prompt_name,
                        prompt_path,
                        namespace,
                        exc,
                    )

    def _load_workspace_tools(self, resource_root: ResourceRoot, tools_root: Path) -> None:
        if not tools_root.is_dir():
            return

        for tool_file in sorted(tools_root.rglob("*.md")):
            resource_filter = self._resource_root_filter(resource_root)
            if resource_filter.ignores(tool_file, is_dir=False):
                continue
            self._load_workspace_markdown_tool(resource_root, tools_root, tool_file)

        for tool_file in sorted(tools_root.rglob("*.py")):
            if tool_file.name == "__init__.py":
                continue
            resource_filter = self._resource_root_filter(resource_root)
            if resource_filter.ignores(tool_file, is_dir=False):
                continue
            try:
                module = self._load_module_from_file(tool_file)
            except Exception as exc:
                logger.error("Failed loading workspace tool module '%s': %s", tool_file, exc, exc_info=True)
                continue

            found_any = False
            for tool_name, tool_impl in self._iter_workspace_tool_exports(module):
                found_any = True
                for namespace in self._resource_root_namespaces(resource_root):
                    try:
                        self.tools.register(namespace, tool_name, tool_impl)
                    except RegistryError as exc:
                        logger.warning(
                            "Resource-root tool '%s' from '%s' collides with an existing registration in '%s': %s",
                            tool_name,
                            tool_file,
                            namespace,
                            exc,
                        )
            if not found_any:
                logger.warning(
                    "Workspace tool module '%s' defines no public tool exports. Skipping.",
                    tool_file,
                )

    def _load_workspace_flows(self, resource_root: ResourceRoot, flows_root: Path) -> None:
        if not flows_root.is_dir():
            return

        resource_filter = self._resource_root_filter(resource_root)
        for flow_file in sorted(flows_root.rglob("*.md")):
            if resource_filter.ignores(flow_file, is_dir=False):
                continue
            self._load_workspace_markdown_flow(resource_root, flows_root, flow_file)

    def _load_workspace_markdown_tool(
        self,
        resource_root: ResourceRoot,
        tools_root: Path,
        tool_file: Path,
    ) -> None:
        default_name = self._workspace_resource_name(tools_root, tool_file.with_suffix(""))
        try:
            document = load_markdown_asset_document(tool_file)
            tool_definition = compile_markdown_tool_definition(document, default_name=default_name)
            loaded_tool = self._load_reference(tool_definition.handler, tool_file.parent)
            wrapped_tool = build_markdown_tool_wrapper(
                tool_definition=tool_definition,
                delegate=loaded_tool,
                registered_name=tool_definition.name or default_name,
            )
        except Exception as exc:
            logger.error(
                "Failed loading workspace markdown tool '%s': %s",
                tool_file,
                exc,
                exc_info=True,
            )
            return

        for namespace in self._resource_root_namespaces(resource_root):
            try:
                self.tools.register(namespace, tool_definition.name or default_name, wrapped_tool)
            except RegistryError as exc:
                logger.warning(
                    "Resource-root markdown tool '%s' from '%s' collides with an existing registration in '%s': %s",
                    tool_definition.name or default_name,
                    tool_file,
                    namespace,
                    exc,
                )

    def _load_workspace_markdown_flow(
        self,
        resource_root: ResourceRoot,
        flows_root: Path,
        flow_file: Path,
    ) -> None:
        default_name = self._workspace_resource_name(flows_root, flow_file.with_suffix(""))
        try:
            document = load_markdown_asset_document(
                flow_file,
                fallback_dirs=self._workspace_prompt_fallback_dirs(),
                prompt_registry=self.prompts,
                context_plugin=WORKSPACE_NAMESPACE,
            )
            definition = compile_markdown_flow_definition(document, default_name=default_name)
            flow_name = str(definition.get("name") or default_name).strip() or default_name

            prompt_definition = dict(definition)
            if "prompt_files" not in prompt_definition and "prompts" in prompt_definition:
                prompt_definition["prompt_files"] = prompt_definition.get("prompts")

            system_prompt, prompt_sources = resolve_prompt_bundle(
                prompt_definition,
                base_dir=flow_file.parent,
                inline_keys=("system_prompt", "prompt"),
                file_keys=("system_prompt_file", "prompt_file"),
                files_key="prompt_files",
                default_files=[],
                fallback_dirs=self._workspace_prompt_fallback_dirs(),
                prompt_registry=self.prompts,
                context_plugin=WORKSPACE_NAMESPACE,
            )

            llm_profile = definition.get("llm_profile")
            tools = coerce_str_list(definition.get("tools"))
            handoff_agents = coerce_str_list(definition.get("handoff_agents"))
            composite_agents = coerce_str_list(definition.get("composite_agents"))
            execution_mode = str(definition.get("execution_mode") or "llm").strip() or "llm"
            deterministic_handler = definition.get("deterministic_handler") or definition.get("handler")
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

            raw_handoff_policies = definition.get("handoff_policies", {})
            if not isinstance(raw_handoff_policies, dict):
                raw_handoff_policies = {}
            handoff_policies = {
                str(target): dict(policy)
                for target, policy in raw_handoff_policies.items()
                if isinstance(target, str) and isinstance(policy, dict)
            }
            raw_default_handoff_policy = definition.get("default_handoff_policy", {})
            if not isinstance(raw_default_handoff_policy, dict):
                raw_default_handoff_policy = {}

            flow_instance = self._load_agent_flow(
                module_ref=definition.get("module"),
                entry_fn_name=definition.get("entry_fn"),
                plugin_root=flow_file.parent,
                agent_name=flow_name,
                plugin_name=WORKSPACE_NAMESPACE,
            )
            if flow_instance is None:
                flow_instance = build_graph_flow_from_metadata(definition)
        except Exception as exc:
            logger.error(
                "Failed loading workspace markdown flow '%s': %s",
                flow_file,
                exc,
                exc_info=True,
            )
            return

        metadata_base = {
            **dict(definition.get("metadata") or {}),
            "markdown_path": str(flow_file.resolve()),
            "resource_root": str(resource_root.path),
        }

        for namespace in self._resource_root_namespaces(resource_root):
            flow_def = FlowDefinition(
                name=flow_name,
                description=str(definition.get("description", "")),
                llm_profile=str(llm_profile) if llm_profile else None,
                tools=[str(item) for item in tools if isinstance(item, str)],
                handoff_agents=[str(item) for item in handoff_agents if isinstance(item, str)],
                execution_mode=execution_mode,
                deterministic_handler=str(deterministic_handler).strip() if deterministic_handler else None,
                composite_agents=[str(item) for item in composite_agents if isinstance(item, str)],
                system_prompt=system_prompt,
                prompt_sources=prompt_sources,
                pre_handlers=pre_handlers,
                step_handlers=step_handlers,
                post_handlers=post_handlers,
                handoff_policies=handoff_policies,
                default_handoff_policy=dict(raw_default_handoff_policy),
                module=str(definition["module"]).strip() if definition.get("module") else None,
                entry_fn=str(definition["entry_fn"]).strip() if definition.get("entry_fn") else None,
                flow_instance=flow_instance,
                metadata={
                    **metadata_base,
                    "plugin": namespace,
                    "plugin_root": str(resource_root.path),
                },
            )
            try:
                self.flows.register(namespace, flow_name, flow_def)
            except RegistryError as exc:
                logger.warning(
                    "Resource-root markdown flow '%s' from '%s' collides with an existing registration in '%s': %s",
                    flow_name,
                    flow_file,
                    namespace,
                    exc,
                )

    def _validate_loaded_flow_references(self) -> None:
        for qualified_flow_name, flow_def in self.flows.items():
            context_plugin = (flow_def.metadata or {}).get("plugin")
            flow_def.tools = self._qualify_existing_tool_refs(
                flow_def.tools,
                owner_name=qualified_flow_name,
                field_name="tools",
                context_plugin=context_plugin,
            )
            flow_def.handoff_agents = self._qualify_existing_flow_refs(
                flow_def.handoff_agents,
                owner_name=qualified_flow_name,
                field_name="handoff_agents",
                context_plugin=context_plugin,
            )
            flow_def.composite_agents = self._qualify_existing_flow_refs(
                flow_def.composite_agents,
                owner_name=qualified_flow_name,
                field_name="composite_agents",
                context_plugin=context_plugin,
            )

            default_agent = flow_def.default_agent_profile
            if default_agent is None:
                continue
            if default_agent.tools is not None:
                default_agent.tools = self._qualify_existing_tool_refs(
                    default_agent.tools,
                    owner_name=f"{qualified_flow_name}.default_agent",
                    field_name="tools",
                    context_plugin=context_plugin,
                )
            default_agent.extra_prompts = self._filter_existing_prompt_refs(
                default_agent.extra_prompts,
                owner_name=f"{qualified_flow_name}.default_agent",
                field_name="extra_prompts",
                context_plugin=context_plugin,
            )

    def _qualify_existing_tool_refs(
        self,
        refs: List[str],
        *,
        owner_name: str,
        field_name: str,
        context_plugin: str | None,
    ) -> List[str]:
        qualified: List[str] = []
        for ref in refs:
            candidate = str(ref or "").strip()
            if not candidate:
                continue
            if candidate == "*":
                return ["*"]
            try:
                resolved = self.tools.qualify(candidate, context_plugin=context_plugin)
            except RegistryError as exc:
                logger.warning(
                    "Flow '%s' has invalid %s ref '%s': %s. Skipping it.",
                    owner_name,
                    field_name,
                    candidate,
                    exc,
                )
                continue
            if resolved not in qualified:
                qualified.append(resolved)
        return qualified

    def _qualify_existing_flow_refs(
        self,
        refs: List[str],
        *,
        owner_name: str,
        field_name: str,
        context_plugin: str | None,
    ) -> List[str]:
        qualified: List[str] = []
        for ref in refs:
            candidate = str(ref or "").strip()
            if not candidate:
                continue
            try:
                resolved = self.flows.qualify(candidate, context_plugin=context_plugin)
            except RegistryError as exc:
                logger.warning(
                    "Flow '%s' has invalid %s ref '%s': %s. Skipping it.",
                    owner_name,
                    field_name,
                    candidate,
                    exc,
                )
                continue
            if resolved not in qualified:
                qualified.append(resolved)
        return qualified

    def _filter_existing_prompt_refs(
        self,
        refs: List[str],
        *,
        owner_name: str,
        field_name: str,
        context_plugin: str | None,
    ) -> List[str]:
        filtered: List[str] = []
        for ref in refs:
            candidate = str(ref or "").strip()
            if not candidate:
                continue
            if not is_prompt_reference(candidate):
                filtered.append(candidate)
                continue
            try:
                resolve_prompt_reference(
                    candidate,
                    prompt_registry=self.prompts,
                    context_plugin=context_plugin,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Flow '%s' has invalid %s ref '%s': %s. Skipping it.",
                    owner_name,
                    field_name,
                    candidate,
                    exc,
                )
                continue
            filtered.append(candidate)
        return filtered

    def _workspace_resource_name(self, root: Path, path: Path) -> str:
        relative = path.resolve().relative_to(root.resolve())
        return ".".join(relative.with_suffix("").parts)

    def _iter_workspace_tool_exports(self, module: types.ModuleType) -> Iterable[tuple[str, Any]]:
        exports = getattr(module, "TOOLS", None)
        if exports is not None:
            yield from self._normalize_workspace_tool_exports(module, exports)
            return

        seen: set[str] = set()
        for name, value in sorted(module.__dict__.items()):
            if name.startswith("_"):
                continue
            if not self._is_workspace_tool_candidate(module, value):
                continue
            if name in seen:
                continue
            seen.add(name)
            yield name, value

    def _normalize_workspace_tool_exports(
        self,
        module: types.ModuleType,
        exports: Any,
    ) -> Iterable[tuple[str, Any]]:
        if isinstance(exports, dict):
            for raw_name, raw_value in exports.items():
                if not isinstance(raw_name, str) or not raw_name.strip():
                    continue
                resolved = self._resolve_workspace_tool_export(module, raw_value)
                if resolved is not None:
                    yield raw_name.strip(), resolved
            return

        if isinstance(exports, (list, tuple, set)):
            for raw_value in exports:
                resolved_name, resolved_value = self._resolve_workspace_tool_export_entry(module, raw_value)
                if resolved_name and resolved_value is not None:
                    yield resolved_name, resolved_value

    def _resolve_workspace_tool_export_entry(
        self,
        module: types.ModuleType,
        raw_value: Any,
    ) -> tuple[str | None, Any | None]:
        if isinstance(raw_value, str):
            candidate = getattr(module, raw_value, None)
            if candidate is not None and self._is_workspace_tool_candidate(module, candidate):
                return raw_value, candidate
            return None, None

        if self._is_workspace_tool_candidate(module, raw_value):
            inferred_name = getattr(raw_value, "__name__", getattr(raw_value, "name", None))
            if isinstance(inferred_name, str) and inferred_name.strip():
                return inferred_name.strip(), raw_value
        return None, None

    def _resolve_workspace_tool_export(self, module: types.ModuleType, raw_value: Any) -> Any | None:
        if isinstance(raw_value, str):
            raw_value = getattr(module, raw_value, None)
        if raw_value is not None and self._is_workspace_tool_candidate(module, raw_value):
            return raw_value
        return None

    def _is_workspace_tool_candidate(self, module: types.ModuleType, value: Any) -> bool:
        if inspect.isfunction(value):
            return value.__module__ == module.__name__
        if isinstance(value, type) and issubclass(value, BaseTool) and value is not BaseTool:
            return value.__module__ == module.__name__
        if isinstance(value, BaseTool):
            return value.__class__.__module__ == module.__name__
        if callable(value):
            return getattr(value.__class__, "__module__", None) == module.__name__
        return False

    def _load_agent_plugin(self, plugin_root: Path) -> None:
        manifest_path = plugin_root / "agent.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(manifest, dict):
            raise ValueError(f"Agent manifest must be a YAML object: {manifest_path}")

        agent_name = str(manifest.get("name") or plugin_root.name)
        self.plugin_roots[agent_name] = plugin_root

        logger.info("Loading agent plugin '%s' from %s", agent_name, plugin_root)

        # Map agent.yaml fields to AgentDefinition
        personality = manifest.get("personality", {})
        system_prompt_file = personality.get("system_prompt")
        rules = personality.get("rules", [])

        system_prompt = ""
        if system_prompt_file:
            prompt_path = plugin_root / system_prompt_file
            if prompt_path.is_file():
                system_prompt = prompt_path.read_text(encoding="utf-8")
        
        if rules:
            rules_text = "\n".join([f"- {r}" for r in rules])
            system_prompt = f"{system_prompt}\n\nRules:\n{rules_text}" if system_prompt else f"Rules:\n{rules_text}"

        tools_manifest = manifest.get("tools", [])
        agent_tools = []
        for t in tools_manifest:
            if isinstance(t, dict) and "id" in t and "handler" in t:
                tool_id = t["id"]
                handler = t["handler"]
                # Register tool globally with plugin prefix to avoid collisions? 
                # For now, let's keep it simple and register with provided ID if not exists
                # In Option B, tools/ are local.
                tool_ref = f"{plugin_root}/tools/{handler}" if not handler.startswith("/") else handler
                if ":" not in tool_ref and "/" in tool_ref:
                    # If it looks like a path but lacks a colon, assume it's path.py:Handler
                    pass

                try:
                    if self._reference_is_ignored(tool_ref, plugin_root):
                        continue
                    loaded_tool = self._load_reference(tool_ref, plugin_root)
                    self.tools.register(agent_name, tool_id, loaded_tool)
                    agent_tools.append(tool_id)
                except RegistryError as exc:
                    logger.error("Tool '%s' for agent '%s' has registry collision: %s", tool_id, agent_name, exc)
                except Exception as exc:
                    logger.error("Failed to load tool '%s' for agent '%s': %s", tool_id, agent_name, exc)

        agent_def = FlowDefinition(
            name=agent_name,
            description=str(manifest.get("description", "")),
            tools=agent_tools,
            system_prompt=system_prompt,
            metadata={
                "plugin": agent_name,
                "plugin_root": str(plugin_root),
                "version": manifest.get("version"),
                "author": manifest.get("author"),
            },
        )
        try:
            self.flows.register(agent_name, agent_name, agent_def)
        except RegistryError as exc:
            logger.error("Agent '%s' registry collision: %s — skipping.", agent_name, exc)

    def _load_plugin_llm_profiles(self, plugin_name: str, llm_profiles: Dict[str, Any]) -> None:
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

    def _load_plugin_prompts(
        self,
        plugin_name: str,
        plugin_root: Path,
        prompts_section: Dict[str, Any],
    ) -> None:
        if not isinstance(prompts_section, dict):
            logger.warning("Plugin '%s' prompts section is not a mapping. Skipping.", plugin_name)
            return

        for prompt_name, reference in prompts_section.items():
            if not isinstance(reference, str):
                logger.warning(
                    "Plugin '%s' prompt '%s' must be a string path. Skipping.",
                    plugin_name,
                    prompt_name,
                )
                continue
            prompt_path = (plugin_root / reference).resolve()
            if not prompt_path.is_file():
                logger.error(
                    "Plugin '%s' prompt '%s' not found at '%s'.",
                    plugin_name,
                    prompt_name,
                    prompt_path,
                )
                continue
            if self._plugin_resource_is_ignored(plugin_root, prompt_path):
                continue
            try:
                self.prompts.register(plugin_name, str(prompt_name), prompt_path.read_text(encoding="utf-8"))
            except RegistryError as exc:
                logger.error(
                    "Plugin '%s' prompt '%s' registry collision: %s",
                    plugin_name,
                    prompt_name,
                    exc,
                )

    def _load_factory_plugin_prompts(self, plugin_name: str, plugin: Plugin) -> None:
        for prompt_name, content in (plugin.prompts or {}).items():
            if not isinstance(prompt_name, str) or not isinstance(content, str):
                continue
            try:
                self.prompts.register(plugin_name, prompt_name, content)
            except RegistryError as exc:
                logger.error(
                    "Plugin '%s' prompt '%s' registry collision: %s",
                    plugin_name,
                    prompt_name,
                    exc,
                )

    def _load_plugin_tools(self, plugin_name: str, plugin_root: Path, tools_section: Dict[str, Any]) -> None:
        if not isinstance(tools_section, dict):
            logger.warning("Plugin '%s' tools section is not a mapping. Skipping.", plugin_name)
            return

        for tool_name, reference in tools_section.items():
            if isinstance(reference, str) and reference.strip().lower().endswith(".md"):
                self._load_markdown_manifest_tool(
                    plugin_name=plugin_name,
                    plugin_root=plugin_root,
                    tool_name=str(tool_name),
                    reference=reference.strip(),
                )
                continue
            try:
                if self._reference_is_ignored(reference, plugin_root):
                    continue
                loaded_tool = self._load_reference(reference, plugin_root)
                self.tools.register(plugin_name, str(tool_name), loaded_tool)
            except RegistryError as exc:
                logger.error(
                    "Plugin '%s' tool '%s' registry collision: %s",
                    plugin_name,
                    tool_name,
                    exc,
                )
            except Exception as exc:
                logger.error(
                    "Plugin '%s' failed to load tool '%s' from '%s': %s",
                    plugin_name,
                    tool_name,
                    reference,
                    exc,
                )

    def _load_markdown_manifest_tool(
        self,
        *,
        plugin_name: str,
        plugin_root: Path,
        tool_name: str,
        reference: str,
    ) -> None:
        markdown_path = (plugin_root / reference).resolve()
        if self._plugin_resource_is_ignored(plugin_root, markdown_path):
            return
        try:
            document = load_markdown_asset_document(markdown_path)
            tool_definition = compile_markdown_tool_definition(document, default_name=tool_name)
            loaded_tool = self._load_reference(tool_definition.handler, markdown_path.parent)
            wrapped_tool = build_markdown_tool_wrapper(
                tool_definition=tool_definition,
                delegate=loaded_tool,
                registered_name=tool_name,
            )
            self.tools.register(plugin_name, tool_name, wrapped_tool)
        except RegistryError as exc:
            logger.error(
                "Plugin '%s' markdown tool '%s' registry collision: %s",
                plugin_name,
                tool_name,
                exc,
            )
        except Exception as exc:
            logger.error(
                "Plugin '%s' failed to load markdown tool '%s' from '%s': %s",
                plugin_name,
                tool_name,
                reference,
                exc,
                exc_info=True,
            )

    def _load_plugin_flows(self, plugin_name: str, plugin_root: Path, flows_section: Dict[str, Any]) -> None:
        if not isinstance(flows_section, dict):
            logger.warning("Plugin '%s' flows section is not a mapping. Skipping.", plugin_name)
            return

        for flow_name, raw_definition in flows_section.items():
            definition = raw_definition if isinstance(raw_definition, dict) else {}
            if self._flow_definition_is_ignored(definition, plugin_root):
                continue
            self._register_flow_definition(
                flow_name=str(flow_name),
                definition=definition,
                plugin_name=plugin_name,
                plugin_root=plugin_root,
            )

    def _load_plugin_agents(self, plugin_name: str, plugin_root: Path, agents_section: Dict[str, Any]) -> None:
        """Backward-compatible alias for loading manifest flows."""
        self._load_plugin_flows(plugin_name, plugin_root, agents_section)

    def _register_flow_definition(
        self,
        flow_name: str,
        definition: Dict[str, Any],
        plugin_name: str,
        plugin_root: Path,
    ) -> None:
        definition = self._resolve_markdown_flow_definition(
            flow_name=flow_name,
            definition=definition,
            plugin_name=plugin_name,
            plugin_root=plugin_root,
        )
        if not definition:
            return

        llm_profile = definition.get("llm_profile")
        tools = definition.get("tools", [])
        if not tools and definition.get("allowed_tools"):
            tools = definition.get("allowed_tools", [])
        handoff_agents = definition.get("handoff_agents", [])

        if not isinstance(tools, list):
            tools = []
        if not isinstance(handoff_agents, list):
            handoff_agents = []

        raw_mode = str(definition.get("execution_mode") or definition.get("mode") or "llm").strip().lower()
        if raw_mode in {"node", "llm"}:
            execution_mode = "llm"
        elif raw_mode in {"deterministic", "python"}:
            execution_mode = "deterministic"
        elif raw_mode in {"composite"}:
            execution_mode = "composite"
        else:
            execution_mode = "llm"

        deterministic_handler = definition.get("deterministic_handler") or definition.get("handler")

        composite_agents = (
            definition.get("composite_agents")
            or definition.get("sub_agents")
            or definition.get("delegate_agents")
            or []
        )
        if not isinstance(composite_agents, list):
            composite_agents = []

        if definition.get("tool_packs"):
            logger.warning(
                "Plugin '%s' agent '%s' uses deprecated 'tool_packs'. Please migrate to 'tools'.",
                plugin_name,
                flow_name,
            )

        prompt_definition = dict(definition)
        if "prompt_files" not in prompt_definition and "prompts" in prompt_definition:
            prompt_definition["prompt_files"] = prompt_definition.get("prompts")

        system_prompt, prompt_sources = resolve_prompt_bundle(
            prompt_definition,
            base_dir=plugin_root,
            inline_keys=("system_prompt", "prompt"),
            file_keys=("system_prompt_file", "prompt_file"),
            files_key="prompt_files",
            default_files=[f"prompts/flows/{flow_name}.md", f"prompts/agents/{flow_name}.md"],
            fallback_dirs=self._workspace_prompt_fallback_dirs(),
            prompt_registry=self.prompts,
            context_plugin=plugin_name,
        )

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

        raw_handoff_policies = definition.get("handoff_policies", {})
        if not isinstance(raw_handoff_policies, dict):
            raw_handoff_policies = {}
        handoff_policies = {
            str(target): dict(policy)
            for target, policy in raw_handoff_policies.items()
            if isinstance(target, str) and isinstance(policy, dict)
        }

        raw_default_handoff_policy = definition.get("default_handoff_policy", {})
        if not isinstance(raw_default_handoff_policy, dict):
            raw_default_handoff_policy = {}

        flow_instance = self._load_agent_flow(
            module_ref=definition.get("module"),
            entry_fn_name=definition.get("entry_fn"),
            plugin_root=plugin_root,
            agent_name=flow_name,
            plugin_name=plugin_name,
        )
        if flow_instance is None:
            flow_instance = build_graph_flow_from_metadata(definition)

        flow_def = FlowDefinition(
            name=flow_name,
            description=str(definition.get("description", "")),
            llm_profile=str(llm_profile) if llm_profile else None,
            tools=[str(item) for item in tools if isinstance(item, str)],
            handoff_agents=[str(item) for item in handoff_agents if isinstance(item, str)],
            execution_mode=execution_mode,
            deterministic_handler=str(deterministic_handler).strip() if deterministic_handler else None,
            composite_agents=[str(item) for item in composite_agents if isinstance(item, str)],
            system_prompt=system_prompt,
            prompt_sources=prompt_sources,
            pre_handlers=pre_handlers,
            step_handlers=step_handlers,
            post_handlers=post_handlers,
            handoff_policies=handoff_policies,
            default_handoff_policy=dict(raw_default_handoff_policy),
            module=str(definition["module"]).strip() if definition.get("module") else None,
            entry_fn=str(definition["entry_fn"]).strip() if definition.get("entry_fn") else None,
            flow_instance=flow_instance,
            metadata={
                **dict(definition.get("metadata") or {}),
                "plugin": plugin_name,
                "plugin_root": str(plugin_root),
            },
        )
        # Read optional default_agent block, falling back to the legacy
        # default_agent_profile key for compatibility.
        raw_dap = definition.get("default_agent") or definition.get("default_agent_profile")
        if isinstance(raw_dap, dict):
            qualified_name = f"{plugin_name}::{flow_name}"
            dap_name = raw_dap.get("name") or qualified_name
            dap_tools_raw = raw_dap.get("tools")
            dap_skills_raw = raw_dap.get("skills")
            dap_tc_raw = raw_dap.get("tool_confirmation") or {}
            if not isinstance(dap_tc_raw, dict):
                dap_tc_raw = {}
            dap_profile = Agent(
                name=str(dap_name),
                flow=qualified_name,
                description=str(raw_dap.get("description", "")),
                llm_profile=str(raw_dap["llm_profile"]) if raw_dap.get("llm_profile") else None,
                extra_prompts=[
                    str(p)
                    for p in raw_dap.get("extra_prompts", [])
                    if isinstance(p, str)
                ],
                skills=(
                    [str(skill) for skill in dap_skills_raw if isinstance(skill, str)]
                    if isinstance(dap_skills_raw, list)
                    else None
                ),
                tools=(
                    [str(t) for t in dap_tools_raw if isinstance(t, str)]
                    if isinstance(dap_tools_raw, list)
                    else None
                ),
                tool_confirmation={
                    "default": str(dap_tc_raw["default"]) if dap_tc_raw.get("default") else None,
                    "overrides": {
                        str(k): str(v)
                        for k, v in (dap_tc_raw.get("overrides") or {}).items()
                        if isinstance(k, str) and isinstance(v, str)
                    },
                },
                source="plugin",
                source_path=None,
            )
            flow_def.default_agent = dap_profile
            logger.debug(
                "Plugin '%s' flow '%s': loaded default_agent '%s'.",
                plugin_name,
                flow_name,
                dap_name,
            )

        try:
            self.flows.register(plugin_name, flow_name, flow_def)
        except RegistryError as exc:
            logger.error(
                "Plugin '%s' flow '%s' registry collision: %s — skipping.",
                plugin_name,
                flow_name,
                exc,
            )

    def _resolve_markdown_flow_definition(
        self,
        *,
        flow_name: str,
        definition: Dict[str, Any],
        plugin_name: str,
        plugin_root: Path,
    ) -> Dict[str, Any]:
        markdown_ref = self._markdown_asset_reference(definition)
        if markdown_ref is None:
            return definition

        markdown_path = (plugin_root / markdown_ref).resolve()
        try:
            document = load_markdown_asset_document(
                markdown_path,
                fallback_dirs=self._workspace_prompt_fallback_dirs(),
                prompt_registry=self.prompts,
                context_plugin=plugin_name,
            )
            compiled = compile_markdown_flow_definition(document, default_name=flow_name)
        except Exception as exc:
            logger.error(
                "Plugin '%s' flow '%s': failed to load markdown definition '%s': %s",
                plugin_name,
                flow_name,
                markdown_path,
                exc,
                exc_info=True,
            )
            return {}

        merged = dict(compiled)
        for key, value in definition.items():
            if key in {"markdown", "markdown_file", "source"} and value == markdown_ref:
                continue
            merged[key] = value
        metadata = dict(compiled.get("metadata") or {})
        metadata["markdown_path"] = str(markdown_path)
        merged["metadata"] = metadata
        return merged

    def _markdown_asset_reference(self, definition: Dict[str, Any]) -> str | None:
        markdown_ref = definition.get("markdown") or definition.get("markdown_file")
        if isinstance(markdown_ref, str) and markdown_ref.strip():
            return markdown_ref.strip()

        source_ref = definition.get("source")
        if isinstance(source_ref, str) and source_ref.strip().lower().endswith(".md"):
            return source_ref.strip()
        return None

    def _load_agent_flow(
        self,
        *,
        module_ref: str | None,
        entry_fn_name: str | None,
        plugin_root: Path,
        agent_name: str,
        plugin_name: str,
    ) -> Any:
        """Load a PocketFlow Flow from a module+entry_fn declaration in plugin.yaml.

        Returns the Flow instance if the factory is found and callable, ``None`` otherwise.
        On any exception, logs at ERROR and returns ``None`` (agent still registers
        without a flow_instance, using the legacy LLM path).
        """
        if not module_ref or not entry_fn_name:
            return None
        try:
            file_path = (plugin_root / module_ref).resolve()
            module = self._load_module_from_file(file_path)
            factory = getattr(module, entry_fn_name, None)
            if not callable(factory):
                logger.error(
                    "Plugin '%s' agent '%s': entry_fn '%s' not found or not callable in '%s'.",
                    plugin_name,
                    agent_name,
                    entry_fn_name,
                    file_path,
                )
                return None
            flow = factory()
            logger.debug(
                "Plugin '%s' agent '%s': flow_instance loaded from '%s:%s'.",
                plugin_name,
                agent_name,
                module_ref,
                entry_fn_name,
            )
            return flow
        except Exception as exc:
            logger.error(
                "Plugin '%s' agent '%s': failed to load flow from '%s:%s': %s",
                plugin_name,
                agent_name,
                module_ref,
                entry_fn_name,
                exc,
                exc_info=True,
            )
            return None

    def _workspace_prompt_fallback_dirs(self) -> tuple[Path, ...]:
        fallback_dirs: list[Path] = [self._workspace_root]
        for resource_root in self._resource_roots:
            fallback_dirs.append(resource_root.path)
            fallback_dirs.append(resource_root.path / "prompts")
        return tuple(dict.fromkeys(fallback_dirs))

    def _reference_is_ignored(
        self,
        reference: Any,
        plugin_root: Path,
    ) -> bool:
        if not isinstance(reference, str):
            return False

        candidate = reference.strip()
        if not candidate or ":" not in candidate:
            return False

        path_part, _ = candidate.split(":", 1)
        file_path = (plugin_root / path_part).resolve()
        return self._plugin_resource_is_ignored(plugin_root, file_path)

    def _flow_definition_is_ignored(
        self,
        definition: Dict[str, Any],
        plugin_root: Path,
    ) -> bool:
        module_ref = definition.get("module")
        if isinstance(module_ref, str) and module_ref.strip():
            module_path = (plugin_root / module_ref).resolve()
            if self._plugin_resource_is_ignored(plugin_root, module_path):
                return True

        prompt_file = definition.get("prompt_file") or definition.get("system_prompt_file")
        if isinstance(prompt_file, str) and prompt_file.strip():
            prompt_path = (plugin_root / prompt_file).resolve()
            if self._plugin_resource_is_ignored(plugin_root, prompt_path):
                return True

        prompt_files = definition.get("prompt_files")
        if not prompt_files and isinstance(definition.get("prompts"), list):
            prompt_files = definition.get("prompts")
        if isinstance(prompt_files, list):
            for prompt_ref in prompt_files:
                if not isinstance(prompt_ref, str) or not prompt_ref.strip():
                    continue
                prompt_path = (plugin_root / prompt_ref).resolve()
                if self._plugin_resource_is_ignored(plugin_root, prompt_path):
                    return True

        return False

    def _plugin_root_is_ignored(self, plugin_root: Path) -> bool:
        resolved = plugin_root.resolve()
        containing_root = resource_root_for_path(resolved, self._resource_roots)
        if containing_root is not None:
            return self._resource_root_filter(containing_root).ignores(resolved, is_dir=True)
        return self._global_plugin_filter.ignores_relative(Path(resolved.name), is_dir=True)

    def _plugin_resource_is_ignored(self, plugin_root: Path, resource_path: Path) -> bool:
        resolved_plugin_root = plugin_root.resolve()
        resolved_resource = resource_path.resolve()
        containing_root = resource_root_for_path(resolved_plugin_root, self._resource_roots)
        if containing_root is not None:
            return self._resource_root_filter(containing_root).ignores(
                resolved_resource,
                is_dir=resolved_resource.is_dir(),
            )
        try:
            relative = resolved_resource.relative_to(resolved_plugin_root)
        except ValueError:
            return False
        return self._global_plugin_filter.ignores_relative(
            Path(resolved_plugin_root.name) / relative,
            is_dir=resolved_resource.is_dir(),
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

    def _resource_root_namespaces(self, resource_root: ResourceRoot) -> tuple[str, ...]:
        namespaces = [resource_root_namespace(resource_root)]
        if is_default_resource_root(resource_root):
            namespaces.append(WORKSPACE_NAMESPACE)
        return tuple(namespaces)

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
            else:
                raise FileNotFoundError(f"Tool implementation file not found: {file_path}")

        if "." not in candidate:
            raise ValueError(
                f"Reference '{reference}' must be an import path (module.Object) or file reference (path.py:Object)."
            )

        module_name, object_name = candidate.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, object_name)

    def _load_from_file(self, file_path: Path, object_name: str) -> Any:
        module_name = self._build_dynamic_module_name(file_path)
        sys.modules.pop(module_name, None)
        module = self._execute_module_from_file(file_path, module_name)

        return getattr(module, object_name)

    def _unload_dynamic_modules(self) -> None:
        for module_name in self._dynamic_module_names:
            sys.modules.pop(module_name, None)
        self._dynamic_module_names.clear()

    def _build_dynamic_module_name(self, file_path: Path) -> str:
        content_hash = hash(file_path.read_bytes())
        token = f"{file_path.resolve()}:{content_hash}"
        return f"pocketcode_dynamic_plugin_{abs(hash(token))}"

    def _execute_module_from_file(self, file_path: Path, module_name: str) -> types.ModuleType:
        module = types.ModuleType(module_name)
        module.__file__ = str(file_path)
        if file_path.name == "__init__.py":
            module.__package__ = module_name
            module.__path__ = [str(file_path.parent)]  # type: ignore[attr-defined]
        sys.modules[module_name] = module
        self._dynamic_module_names.add(module_name)
        source = file_path.read_text(encoding="utf-8")
        code = compile(source, str(file_path), "exec")
        exec(code, module.__dict__)
        return module
