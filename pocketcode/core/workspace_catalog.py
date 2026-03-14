from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import sys
import types
from pathlib import Path
from typing import Any, Dict, Iterable, List

from pocketcode.core.interfaces import BaseTool
from pocketcode.core.namespace_registry import NamespaceRegistry, RegistryError, RegistryHolder
from pocketcode.core.prompt_loader import (
    coerce_str_list,
    is_prompt_reference,
    resolve_prompt_bundle,
    resolve_prompt_reference,
)
from pocketcode.core.markdown_profiles import parse_markdown_front_matter
from pocketcode.core.discovery_rules import DiscoveryFilter
from pocketcode.core.markdown_assets import (
    build_markdown_tool_wrapper,
    compile_markdown_agent_definition,
    compile_markdown_hook_definition,
    compile_markdown_flow_definition,
    compile_markdown_tool_definition,
    load_markdown_asset_document,
)
from pocketcode.core.resource_roots import (
    ResourceRoot,
    discover_resource_roots,
    primary_resource_root,
    resource_root_for_path,
    resource_root_namespace,
)
from pocketcode.core.runtime_models import Agent, FlowDefinition, HOOK_PHASES, HookDefinition
from pocketcode.core.tool_conventions import TOOL_MODULE_SUFFIX, iter_convention_tool_files
from pocketcode.core.workspace_namespaces import WorkspaceNamespace, namespace_asset_name

logger = logging.getLogger(__name__)


def _coerce_str_dict(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key).strip(): str(item).strip()
        for key, item in value.items()
        if str(key).strip() and str(item).strip()
    }


_EXECUTABLE_MARKDOWN_KEYS = frozenset(
    {
        "name",
        "description",
        "execution_mode",
        "llm_profile",
        "tools",
        "tool_files",
        "prompt_files",
        "prompts",
        "handoff_agents",
        "default_agent",
        "default_agent_profile",
        "composite_agents",
        "module",
        "entry_fn",
        "vm_entry",
        "vm_module",
        "vm_modules",
        "vm_module_prefixes",
        "vm_file",
        "vm_files",
        "vm_source",
    }
)

_SELF_CONTAINED_AGENT_FLOW_KEYS = frozenset(
    {
        "execution_mode",
        "llm_profile",
        "tools",
        "tool_files",
        "prompt_files",
        "prompts",
        "handoff_agents",
        "composite_agents",
        "module",
        "entry_fn",
        "vm_entry",
        "vm_module",
        "vm_modules",
        "vm_module_prefixes",
        "vm_file",
        "vm_files",
        "vm_source",
        "pre",
        "pre_steps",
        "steps",
        "exec",
        "exec_steps",
        "post",
        "post_steps",
        "deterministic_handler",
        "handler",
        "handoff_policies",
        "default_handoff_policy",
    }
)


class WorkspaceCatalog:
    def __init__(self, config: Dict[str, Any], workspace_root: str | Path):
        self._config = config
        self._workspace_root = Path(workspace_root).resolve()
        self._resource_roots: list[ResourceRoot] = discover_resource_roots(self._workspace_root)
        self._primary_resource_root = primary_resource_root(self._workspace_root, self._resource_roots)

        self.tools: NamespaceRegistry[Any] = NamespaceRegistry()
        self.flows: NamespaceRegistry[FlowDefinition] = NamespaceRegistry()
        self.agents = self.flows
        self.hooks: NamespaceRegistry[HookDefinition] = NamespaceRegistry()
        self.prompts: NamespaceRegistry[str] = NamespaceRegistry()
        self.llm_profiles: Dict[str, Dict[str, Any]] = {}
        self.namespace_roots: Dict[str, Path] = {}
        self._holder: RegistryHolder = RegistryHolder()
        self._dynamic_module_names: set[str] = set()
        self._loaded_external_tool_files: Dict[tuple[str, Path], list[str]] = {}
        self._resource_root_namespace_packs = self._build_resource_root_namespace_packs()
        self._resource_root_filters: Dict[Path, DiscoveryFilter] = self._build_resource_root_filters()
        self._global_catalog_filter = DiscoveryFilter.from_root(
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
        self.hooks = NamespaceRegistry()
        self.prompts = NamespaceRegistry()
        self.llm_profiles.clear()
        self.namespace_roots.clear()
        self._loaded_external_tool_files.clear()
        self._resource_roots = discover_resource_roots(self._workspace_root)
        self._primary_resource_root = primary_resource_root(self._workspace_root, self._resource_roots)
        self._resource_root_namespace_packs = self._build_resource_root_namespace_packs()
        self._resource_root_filters = self._build_resource_root_filters()
        self._global_catalog_filter = DiscoveryFilter.from_root(
            self._workspace_root,
            ignore_dir=self._workspace_root,
        )

    def load(self) -> None:
        self.clear()

        namespace_roots: list[WorkspaceNamespace] = []
        for resource_root in self._resource_roots:
            namespace_roots.extend(self._resource_root_namespace_pack_roots(resource_root))
        namespace_roots.extend(self._configured_workspace_namespaces())
        namespace_roots = self._dedupe_namespaces(namespace_roots)
        self._register_catalog_namespaces(namespace_roots)

        self._load_workspace_prompts_only()
        self._load_workspace_hooks_only()
        self._load_workspace_namespace_prompts(namespace_roots)
        self._load_workspace_namespace_tools(namespace_roots)
        self._load_workspace_namespace_programs(namespace_roots)
        self._load_workspace_namespace_agent_programs(namespace_roots)

        self._load_workspace_tools_only()
        self._load_workspace_flows_only()
        self._load_workspace_executable_agents_only()
        self._validate_loaded_flow_references()

        logger.info(
            "Workspace catalog load complete. namespaces=%d, hooks=%d, tools=%d, flows=%d, llm_profiles=%d",
            len(self.namespace_roots),
            len(self.hooks),
            len(self.tools),
            len(self.flows),
            len(self.llm_profiles),
        )
        # Atomic registry swap — new sessions immediately see fresh state
        self._holder.swap(self)

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

        context_namespace = (agent.metadata or {}).get("namespace")

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
            elif context_namespace and self.tools.has_local(context_namespace, tool_ref):
                qname = f"{context_namespace}.{tool_ref}"  # local namespace owns it
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

    def _dedupe_namespaces(self, namespaces: list[WorkspaceNamespace]) -> list[WorkspaceNamespace]:
        deduped: list[WorkspaceNamespace] = []
        seen_keys: set[tuple[str, Path, str | None]] = set()
        for namespace in namespaces:
            resolved = namespace.path.resolve()
            key = (namespace.name, resolved, namespace.filename_prefix)
            if key in seen_keys:
                continue
            deduped.append(
                WorkspaceNamespace(name=namespace.name, path=resolved, filename_prefix=namespace.filename_prefix)
            )
            seen_keys.add(key)
        return deduped

    def _register_catalog_namespaces(self, namespaces: list[WorkspaceNamespace]) -> None:
        for namespace in namespaces:
            self.namespace_roots.setdefault(namespace.name, namespace.path.resolve())

    def _configured_workspace_paths(self) -> list[Path]:
        runtime = self._config.get("runtime", {}) if isinstance(self._config, dict) else {}
        raw_paths = runtime.get("workspace_paths")
        if not isinstance(raw_paths, list):
            raw_paths = []

        resolved_paths: list[Path] = []
        seen: set[Path] = set()
        for raw_path in raw_paths:
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            candidate = Path(raw_path).expanduser()
            if not candidate.is_absolute():
                candidate = (self._workspace_root / candidate).resolve()
            else:
                candidate = candidate.resolve()
            if candidate in seen:
                continue
            seen.add(candidate)
            resolved_paths.append(candidate)
        return resolved_paths

    def _load_workspace_prompts_only(self) -> None:
        for resource_root in self._resource_roots:
            self._load_workspace_root_prompts(resource_root)

    def _load_workspace_tools_only(self) -> None:
        for resource_root in self._resource_roots:
            self._load_workspace_root_tools(resource_root)

    def _load_workspace_hooks_only(self) -> None:
        for resource_root in self._resource_roots:
            self._load_workspace_root_hooks(resource_root)

    def _load_workspace_flows_only(self) -> None:
        for resource_root in self._resource_roots:
            self._load_workspace_root_flows(resource_root)

    def _configured_workspace_namespaces(self) -> list[WorkspaceNamespace]:
        return self._workspace_namespaces_from_paths(self._configured_workspace_paths())

    def _workspace_namespaces_from_paths(self, paths: list[Path]) -> list[WorkspaceNamespace]:
        namespaces: list[WorkspaceNamespace] = []
        seen_names: set[str] = set()
        for candidate in paths:
            resolved = candidate.resolve()
            for namespace in self._namespaces_for_configured_path(resolved):
                if namespace.name in seen_names:
                    continue
                namespaces.append(namespace)
                seen_names.add(namespace.name)
        return namespaces

    def _namespaces_for_configured_path(self, path: Path) -> list[WorkspaceNamespace]:
        resolved = Path(path).resolve()
        if not resolved.is_dir() or self._catalog_root_is_ignored(resolved):
            return []
        if resolved in self._resource_root_namespace_packs or any(
            resource_root.path.resolve() == resolved for resource_root in self._resource_roots
        ):
            return []
        if not self._path_is_namespace_root(resolved):
            return []
        namespace_name = resolved.name.lstrip(".") or resolved.name
        if not namespace_name:
            return []
        return [WorkspaceNamespace(name=namespace_name, path=resolved)]

    def _path_is_namespace_root(self, path: Path) -> bool:
        resolved = Path(path).resolve()
        if not resolved.is_dir() or self._catalog_root_is_ignored(resolved):
            return False
        return any(
            child.is_file()
            and (
                child.name.endswith(".md")
                or child.name.endswith(TOOL_MODULE_SUFFIX)
            )
            for child in resolved.iterdir()
        )

    def _build_resource_root_namespace_packs(self) -> dict[Path, set[str]]:
        packs: dict[Path, set[str]] = {}
        for resource_root in self._resource_roots:
            namespace_names = self._flat_namespace_names_for_root(resource_root.path)
            if namespace_names:
                packs[resource_root.path.resolve()] = namespace_names
        return packs

    def _resource_root_namespace_pack_roots(self, resource_root: ResourceRoot) -> list[WorkspaceNamespace]:
        namespaces: list[WorkspaceNamespace] = []
        for namespace_name in sorted(self._resource_root_namespace_packs.get(resource_root.path.resolve(), set())):
            namespaces.append(
                WorkspaceNamespace(
                    name=namespace_name,
                    path=resource_root.path,
                    filename_prefix=f"{namespace_name}.",
                )
            )
        return namespaces

    def _flat_namespace_names_for_root(self, root: Path) -> set[str]:
        names: set[str] = set()
        resolved_root = root.resolve()
        for path in resolved_root.iterdir():
            if not path.is_file():
                continue
            name = path.name
            parts = name.split(".")
            if name.endswith(".agent.yaml") or name.endswith(".tool.md"):
                continue
            if name.endswith(".prompt.md") or name.endswith(".agent.md"):
                if len(parts) < 4:
                    continue
            elif name.endswith(TOOL_MODULE_SUFFIX):
                if len(parts) < 4:
                    continue
            elif name.endswith(".md"):
                if len(parts) < 3:
                    continue
            else:
                continue

            namespace_name = parts[0].strip()
            if namespace_name:
                names.add(namespace_name)
        return names

    def _namespace_pack_file_matches(self, namespace: WorkspaceNamespace, asset_path: Path, *, suffix: str) -> bool:
        return bool(namespace_asset_name(namespace.path, asset_path, suffix=suffix, filename_prefix=namespace.filename_prefix))

    def _load_workspace_namespace_prompts(
        self,
        namespaces: list[WorkspaceNamespace],
    ) -> None:
        for namespace in namespaces:
            for prompt_path in sorted(namespace.path.glob("*.prompt.md")):
                if not self._namespace_pack_file_matches(namespace, prompt_path, suffix=".prompt.md"):
                    continue
                if self._catalog_resource_is_ignored(namespace.path, prompt_path):
                    continue
                prompt_name = namespace_asset_name(
                    namespace.path,
                    prompt_path,
                    suffix=".prompt.md",
                    filename_prefix=namespace.filename_prefix,
                )
                if not prompt_name:
                    continue
                _front_matter, prompt_text = parse_markdown_front_matter(
                    prompt_path.read_text(encoding="utf-8")
                )
                try:
                    self.prompts.register(namespace.name, prompt_name, prompt_text.strip())
                except RegistryError as exc:
                    logger.warning(
                        "Workspace namespace prompt '%s' from '%s' collides in '%s': %s",
                        prompt_name,
                        prompt_path,
                        namespace.name,
                        exc,
                    )

    def _load_workspace_namespace_tools(
        self,
        namespaces: list[WorkspaceNamespace],
    ) -> None:
        for namespace in namespaces:
            for tool_path in iter_convention_tool_files(namespace.path):
                if not self._namespace_pack_file_matches(namespace, tool_path, suffix=TOOL_MODULE_SUFFIX):
                    continue
                if self._catalog_resource_is_ignored(namespace.path, tool_path):
                    continue
                self._load_external_tool_module(
                    namespace_name=namespace.name,
                    registration_root=namespace.path,
                    tool_path=tool_path,
                    owner_name=f"{namespace.name} namespace",
                )

    def _load_workspace_namespace_programs(
        self,
        namespaces: list[WorkspaceNamespace],
    ) -> None:
        for namespace in namespaces:
            for program_path in self._iter_workspace_namespace_program_paths(namespace.path):
                if not self._namespace_pack_file_matches(namespace, program_path, suffix=".md"):
                    continue
                if self._catalog_resource_is_ignored(namespace.path, program_path):
                    continue
                try:
                    document = load_markdown_asset_document(
                        program_path,
                        fallback_dirs=self._workspace_namespace_prompt_fallback_dirs(namespace.path),
                        prompt_registry=self.prompts,
                        context_namespace=namespace.name,
                    )
                    if not self._is_workspace_namespace_program_candidate(program_path, document):
                        continue
                    default_name = self._workspace_namespace_program_name(namespace, program_path)
                    if not default_name:
                        continue
                    definition = compile_markdown_flow_definition(document, default_name=default_name)
                    flow_name = str(definition.get("name") or default_name).strip() or default_name
                    metadata = dict(definition.get("metadata") or {})
                    metadata["markdown_path"] = str(program_path.resolve())
                    metadata["workspace_namespace_root"] = str(namespace.path)
                    definition["metadata"] = metadata
                    self._load_flow_definition_tool_files(
                        definition=definition,
                        namespace_name=namespace.name,
                        registration_root=namespace.path,
                        source_dir=program_path.parent,
                        owner_name=f"{namespace.name}.{flow_name}",
                    )
                    self._register_flow_definition(
                        flow_name=flow_name,
                        definition=definition,
                        namespace_name=namespace.name,
                        namespace_root=namespace.path,
                    )
                except Exception as exc:
                    logger.error(
                        "Failed loading workspace namespace program '%s': %s",
                        program_path,
                        exc,
                        exc_info=True,
                    )

    def _load_workspace_namespace_agent_programs(
        self,
        namespaces: list[WorkspaceNamespace],
    ) -> None:
        for namespace in namespaces:
            for agent_path in sorted(namespace.path.glob("*.agent.md")):
                if not self._namespace_pack_file_matches(namespace, agent_path, suffix=".agent.md"):
                    continue
                if self._catalog_resource_is_ignored(namespace.path, agent_path):
                    continue
                default_name = namespace_asset_name(
                    namespace.path,
                    agent_path,
                    suffix=".agent.md",
                    filename_prefix=namespace.filename_prefix,
                )
                if not default_name:
                    continue
                self._load_executable_markdown_agent(
                    agent_path=agent_path,
                    authoring_namespace=namespace.name,
                    registration_root=namespace.path,
                    fallback_dirs=self._workspace_namespace_prompt_fallback_dirs(namespace.path),
                    default_agent_name=default_name,
                    default_flow_name=default_name,
                    target_source="namespace",
                )

    def _load_workspace_root_prompts(self, resource_root: ResourceRoot) -> None:
        resource_filter = self._resource_root_filter(resource_root)
        for prompt_path in sorted(resource_root.path.glob("*.prompt.md")):
            if self._is_resource_root_namespace_pack_asset(resource_root.path, prompt_path):
                continue
            if resource_filter.ignores(prompt_path, is_dir=False):
                continue
            prompt_name = self._flat_resource_asset_name(prompt_path, suffix=".prompt.md")
            if not prompt_name:
                continue
            _front_matter, prompt_text = parse_markdown_front_matter(prompt_path.read_text(encoding="utf-8"))
            for namespace in self._resource_root_namespaces(resource_root):
                try:
                    self.prompts.register(namespace, prompt_name, prompt_text.strip())
                except RegistryError as exc:
                    logger.warning(
                        "Resource-root prompt '%s' at '%s' collides with an existing registration in '%s': %s",
                        prompt_name,
                        prompt_path,
                        namespace,
                        exc,
                    )
        for prompts_root in self._workspace_prompt_roots(resource_root.path):
            for prompt_path in sorted(path for path in prompts_root.rglob("*.md") if path.is_file()):
                if resource_filter.ignores(prompt_path, is_dir=False):
                    continue
                prompt_name = self._workspace_asset_name(prompts_root, prompt_path, suffix=".md")
                if not prompt_name:
                    continue
                _front_matter, prompt_text = parse_markdown_front_matter(prompt_path.read_text(encoding="utf-8"))
                for namespace in self._resource_root_namespaces(resource_root):
                    try:
                        self.prompts.register(namespace, prompt_name, prompt_text.strip())
                    except RegistryError as exc:
                        logger.warning(
                            "Resource-root prompt '%s' at '%s' collides with an existing registration in '%s': %s",
                            prompt_name,
                            prompt_path,
                            namespace,
                            exc,
                        )

    def _load_workspace_root_hooks(self, resource_root: ResourceRoot) -> None:
        resource_filter = self._resource_root_filter(resource_root)
        for hook_path, default_name in self._iter_workspace_hook_files(resource_root):
            if resource_filter.ignores(hook_path, is_dir=False):
                continue
            self._load_workspace_root_hook(resource_root, hook_path, default_name=default_name)

    def _load_workspace_root_tools(self, resource_root: ResourceRoot) -> None:
        resource_filter = self._resource_root_filter(resource_root)

        for tool_file in sorted(resource_root.path.glob("*.tool.md")):
            if self._is_resource_root_namespace_pack_asset(resource_root.path, tool_file):
                continue
            if resource_filter.ignores(tool_file, is_dir=False):
                continue
            self._load_workspace_root_markdown_tool(resource_root, tool_file)

        for tool_file in sorted(resource_root.path.glob(f"*{TOOL_MODULE_SUFFIX}")):
            if self._is_resource_root_namespace_pack_asset(resource_root.path, tool_file):
                continue
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

        for tools_root, prefix in self._workspace_tool_roots(resource_root.path):
            for tool_file in sorted(path for path in tools_root.rglob("*.tool.md") if path.is_file()):
                if resource_filter.ignores(tool_file, is_dir=False):
                    continue
                asset_name = self._workspace_asset_name(tools_root, tool_file, suffix=".tool.md")
                self._load_workspace_root_markdown_tool(
                    resource_root,
                    tool_file,
                    default_name=self._prefix_asset_name(prefix, asset_name),
                )

            for tool_file in iter_convention_tool_files(tools_root):
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

    def _load_workspace_root_hook(
        self,
        resource_root: ResourceRoot,
        hook_file: Path,
        *,
        default_name: str | None = None,
    ) -> None:
        if default_name is None:
            if hook_file.name.endswith(".hook.md"):
                default_name = self._flat_resource_asset_name(hook_file, suffix=".hook.md")
            elif hook_file.name.endswith(".hook.yaml"):
                default_name = self._flat_resource_asset_name(hook_file, suffix=".hook.yaml")
        try:
            if hook_file.suffix.lower() == ".md":
                document = load_markdown_asset_document(hook_file)
                definition = compile_markdown_hook_definition(document, default_name=default_name or hook_file.stem)
            else:
                import yaml

                definition = yaml.safe_load(hook_file.read_text(encoding="utf-8")) or {}
            if not isinstance(definition, dict):
                raise ValueError("Hook definition root must be a mapping.")
            hook_name = str(definition.get("name") or default_name or hook_file.stem).strip()
            if not hook_name:
                raise ValueError("Hook definition is missing a name.")
            raw_phases = definition.get("phases")
            if not isinstance(raw_phases, dict):
                raw_phases = {}
            phases = {
                str(phase_name).strip(): str(phase_source).strip()
                for phase_name, phase_source in raw_phases.items()
                if str(phase_name).strip() in HOOK_PHASES and isinstance(phase_source, str) and phase_source.strip()
            }
            if not phases:
                raise ValueError(f"Hook '{hook_name}' defines no supported hook phases.")
            hook_definition = HookDefinition(
                name=hook_name,
                description=str(definition.get("description", "")),
                phases=phases,
                source="workspace" if resource_root.origin == "workspace" else "namespace",
                source_path=hook_file.resolve(),
                metadata={"resource_root": str(resource_root.path)},
            )
        except Exception as exc:
            logger.error("Failed loading workspace hook '%s': %s", hook_file, exc, exc_info=True)
            return

        for namespace in self._resource_root_namespaces(resource_root):
            try:
                self.hooks.register(namespace, hook_definition.name, hook_definition)
            except RegistryError as exc:
                logger.warning(
                    "Resource-root hook '%s' from '%s' collides with an existing registration in '%s': %s",
                    hook_definition.name,
                    hook_file,
                    namespace,
                    exc,
                )

    def _load_workspace_root_flows(self, resource_root: ResourceRoot) -> None:
        resource_filter = self._resource_root_filter(resource_root)
        for flow_file in sorted(resource_root.path.glob("*.md")):
            if flow_file.name.endswith(".prompt.md") or flow_file.name.endswith(".tool.md") or flow_file.name.endswith(".agent.md") or flow_file.name.endswith(".agent.yaml") or flow_file.name.endswith(".hook.md") or flow_file.name.endswith(".hook.yaml"):
                continue
            if self._is_resource_root_namespace_pack_asset(resource_root.path, flow_file):
                continue
            if resource_filter.ignores(flow_file, is_dir=False):
                continue
            self._load_workspace_root_markdown_flow(resource_root, flow_file)

    def _load_workspace_executable_agents_only(self) -> None:
        for resource_root in self._resource_roots:
            self._load_workspace_root_executable_agents(resource_root)

    def _iter_workspace_namespace_program_paths(self, namespace_root: Path) -> list[Path]:
        return sorted(
            path
            for path in namespace_root.glob("*.md")
            if not path.name.endswith(".prompt.md")
            if not path.name.endswith(".tool.md")
            if not path.name.endswith(".agent.md")
            if not path.name.endswith(".hook.md")
        )

    def _workspace_namespace_program_name(self, namespace: WorkspaceNamespace, program_path: Path) -> str:
        return namespace_asset_name(
            namespace.path,
            program_path,
            suffix=".md",
            filename_prefix=namespace.filename_prefix,
        )

    def _is_workspace_namespace_program_candidate(
        self,
        program_path: Path,
        document: Any,
    ) -> bool:
        if any(block.content.strip() for block in document.find_blocks(languages=("vm", "stackvm"))):
            return True
        front_matter = document.front_matter if isinstance(document.front_matter, dict) else {}
        return any(key in front_matter for key in _EXECUTABLE_MARKDOWN_KEYS)

    def _load_workspace_root_markdown_tool(
        self,
        resource_root: ResourceRoot,
        tool_file: Path,
        *,
        default_name: str | None = None,
    ) -> None:
        default_name = default_name or self._flat_resource_asset_name(tool_file, suffix=".tool.md")
        if not default_name:
            return
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

    def _load_flow_definition_tool_files(
        self,
        *,
        definition: Dict[str, Any],
        namespace_name: str,
        registration_root: Path,
        source_dir: Path,
        owner_name: str,
    ) -> None:
        tool_files = coerce_str_list(definition.get("tool_files"))
        if not tool_files:
            return

        loaded_tool_names: list[str] = []
        for tool_ref in tool_files:
            tool_path = Path(tool_ref).expanduser()
            if not tool_path.is_absolute():
                tool_path = (source_dir / tool_ref).resolve()
            else:
                tool_path = tool_path.resolve()

            loaded_tool_names.extend(
                self._load_external_tool_module(
                    namespace_name=namespace_name,
                    registration_root=registration_root,
                    tool_path=tool_path,
                    owner_name=owner_name,
                )
            )

        if loaded_tool_names and not coerce_str_list(definition.get("tools")):
            definition["tools"] = list(dict.fromkeys(loaded_tool_names))

    def _load_external_tool_module(
        self,
        *,
        namespace_name: str,
        registration_root: Path,
        tool_path: Path,
        owner_name: str,
    ) -> list[str]:
        resolved_tool_path = Path(tool_path).resolve()
        cache_key = (namespace_name, resolved_tool_path)
        cached = self._loaded_external_tool_files.get(cache_key)
        if cached is not None:
            return list(cached)

        if not resolved_tool_path.is_file():
            logger.error(
                "Flow '%s' references missing tool file '%s'.",
                owner_name,
                resolved_tool_path,
            )
            return []
        if self._catalog_resource_is_ignored(registration_root, resolved_tool_path):
            return []
        if resolved_tool_path.suffix.lower() != ".py":
            logger.error(
                "Flow '%s' references unsupported tool file '%s'. Expected a Python module, usually '*%s'.",
                owner_name,
                resolved_tool_path,
                TOOL_MODULE_SUFFIX,
            )
            return []

        try:
            module = self._load_module_from_file(resolved_tool_path)
        except Exception as exc:
            logger.error(
                "Failed loading tool module '%s' for flow '%s': %s",
                resolved_tool_path,
                owner_name,
                exc,
                exc_info=True,
            )
            return []

        loaded_tool_names: list[str] = []
        found_any = False
        for tool_name, tool_impl in self._iter_workspace_tool_exports(module):
            found_any = True
            try:
                self.tools.register(namespace_name, tool_name, tool_impl)
            except RegistryError as exc:
                logger.warning(
                    "Tool '%s' from '%s' collides in '%s': %s",
                    tool_name,
                    resolved_tool_path,
                    namespace_name,
                    exc,
                )
            loaded_tool_names.append(tool_name)

        if not found_any:
            logger.warning(
                "Tool module '%s' for flow '%s' defines no public tool exports. Skipping.",
                resolved_tool_path,
                owner_name,
            )

        deduped = list(dict.fromkeys(loaded_tool_names))
        self._loaded_external_tool_files[cache_key] = deduped
        return deduped

    def _load_workspace_markdown_flow(
        self,
        resource_root: ResourceRoot,
        flows_root: Path,
        flow_file: Path,
    ) -> None:
        default_name = self._workspace_resource_name(flows_root, flow_file.with_suffix(""))
        namespace_name = resource_root_namespace(resource_root)
        try:
            document = load_markdown_asset_document(
                flow_file,
                fallback_dirs=self._workspace_prompt_fallback_dirs(),
                prompt_registry=self.prompts,
                context_namespace=namespace_name,
            )
            definition = compile_markdown_flow_definition(document, default_name=default_name)
            flow_name = str(definition.get("name") or default_name).strip() or default_name
            self._apply_adjacent_markdown_resource_defaults(
                definition=definition,
                registration_root=resource_root.path,
                markdown_path=flow_file,
            )
            self._load_flow_definition_tool_files(
                definition=definition,
                namespace_name=namespace_name,
                registration_root=resource_root.path,
                source_dir=flow_file.parent,
                owner_name=f"{namespace_name}.{flow_name}",
            )

            system_prompt, prompt_sources = resolve_prompt_bundle(
                definition,
                base_dir=flow_file.parent,
                inline_keys=("system_prompt", "prompt"),
                file_keys=("system_prompt_file", "prompt_file"),
                files_key="prompt_files",
                default_files=[],
                fallback_dirs=self._workspace_prompt_fallback_dirs(),
                prompt_registry=self.prompts,
                context_namespace=namespace_name,
            )

            llm_profile = definition.get("llm_profile")
            tools = coerce_str_list(definition.get("tools"))
            handoff_agents = coerce_str_list(definition.get("handoff_agents"))
            composite_agents = coerce_str_list(definition.get("composite_agents"))
            execution_mode = str(
                definition.get("execution_mode")
                or ("vm" if any(definition.get(key) for key in ("vm_source", "vm_file", "vm_module", "vm_files", "vm_modules")) else "llm")
            ).strip() or "llm"
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

            flow_instance = None
            if execution_mode.lower() != "vm":
                flow_instance = self._load_agent_flow(
                    module_ref=definition.get("module"),
                    entry_fn_name=definition.get("entry_fn"),
                    namespace_root=flow_file.parent,
                    agent_name=flow_name,
                    namespace_name=namespace_name,
                )
                if flow_instance is None and any(definition.get(k) for k in ("nodes", "mermaid", "graph", "dot")):
                    raise ValueError("Graph flows no longer supported. Use StackVM instead.")
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
                vm_entry=str(definition["vm_entry"]).strip() if definition.get("vm_entry") else None,
                vm_module=str(definition["vm_module"]).strip() if definition.get("vm_module") else None,
                vm_modules=coerce_str_list(definition.get("vm_modules")),
                vm_module_prefixes=_coerce_str_dict(definition.get("vm_module_prefixes")),
                vm_file=str(definition["vm_file"]).strip() if definition.get("vm_file") else None,
                vm_files=coerce_str_list(definition.get("vm_files")),
                vm_source=str(definition["vm_source"]).strip() if definition.get("vm_source") else None,
                metadata={
                    **metadata_base,
                    "namespace": namespace,
                    "namespace_root": str(resource_root.path),
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

    def _load_workspace_root_markdown_flow(
        self,
        resource_root: ResourceRoot,
        flow_file: Path,
    ) -> None:
        if not self._flat_resource_asset_name(flow_file, suffix=".md"):
            return
        self._load_workspace_markdown_flow(resource_root, resource_root.path, flow_file)

    def _load_workspace_root_executable_agents(self, resource_root: ResourceRoot) -> None:
        resource_filter = self._resource_root_filter(resource_root)
        authoring_namespace = resource_root_namespace(resource_root)

        for agent_path in sorted(resource_root.path.glob("*.agent.md")):
            if self._is_resource_root_namespace_pack_asset(resource_root.path, agent_path):
                continue
            if resource_filter.ignores(agent_path, is_dir=False):
                continue
            default_name = self._flat_resource_asset_name(agent_path, suffix=".agent.md")
            if not default_name:
                continue
            self._load_executable_markdown_agent(
                agent_path=agent_path,
                authoring_namespace=authoring_namespace,
                registration_root=resource_root.path,
                fallback_dirs=self._workspace_prompt_fallback_dirs(),
                default_agent_name=default_name,
                default_flow_name=f"agents.{default_name}",
                target_source="workspace",
            )

        for agents_root, prefix in self._workspace_agent_roots(resource_root.path):
            for agent_path in sorted(path for path in agents_root.rglob("*.agent.md") if path.is_file()):
                if resource_filter.ignores(agent_path, is_dir=False):
                    continue
                asset_name = self._workspace_asset_name(agents_root, agent_path, suffix=".agent.md")
                default_name = self._prefix_asset_name(prefix, asset_name)
                if not default_name:
                    continue
                self._load_executable_markdown_agent(
                    agent_path=agent_path,
                    authoring_namespace=authoring_namespace,
                    registration_root=resource_root.path,
                    fallback_dirs=self._workspace_prompt_fallback_dirs(),
                    default_agent_name=default_name,
                    default_flow_name=f"agents.{default_name}",
                    target_source="workspace",
                )

    def _workspace_agent_roots(self, resource_root_path: Path) -> list[tuple[Path, str | None]]:
        roots: list[tuple[Path, str | None]] = []
        seen: set[Path] = set()

        agents_root = resource_root_path / "agents"
        if agents_root.is_dir():
            resolved = agents_root.resolve()
            seen.add(resolved)
            roots.append((agents_root, None))

        for path in sorted(candidate for candidate in resource_root_path.iterdir() if candidate.is_dir()):
            if not path.name.startswith("agent."):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            roots.append((path, path.name[len("agent."):].strip() or None))

        return roots

    def _load_executable_markdown_agent(
        self,
        *,
        agent_path: Path,
        authoring_namespace: str,
        registration_root: Path,
        fallback_dirs: tuple[Path, ...],
        default_agent_name: str,
        default_flow_name: str,
        target_source: str,
    ) -> None:
        try:
            document = load_markdown_asset_document(
                agent_path,
                fallback_dirs=fallback_dirs,
                prompt_registry=self.prompts,
                context_namespace=authoring_namespace,
            )
            definition = compile_markdown_agent_definition(document, default_name=default_agent_name)
            if not self._is_self_contained_agent_candidate(definition):
                return

            flow_name = str(definition.get("flow") or default_flow_name).strip() or default_flow_name
            self._apply_adjacent_markdown_resource_defaults(
                definition=definition,
                registration_root=registration_root,
                markdown_path=agent_path,
            )
            self._load_flow_definition_tool_files(
                definition=definition,
                namespace_name=authoring_namespace,
                registration_root=registration_root,
                source_dir=agent_path.parent,
                owner_name=f"{authoring_namespace}.{flow_name}",
            )
            flow_def, target_namespace, local_flow_name = self._build_flow_definition_from_agent_markdown(
                definition=definition,
                flow_name=flow_name,
                authoring_namespace=authoring_namespace,
                registration_root=registration_root,
                agent_path=agent_path,
                target_source=target_source,
            )
        except Exception as exc:
            logger.error(
                "Failed loading executable markdown agent '%s': %s",
                agent_path,
                exc,
                exc_info=True,
            )
            return

        try:
            self.flows.register(target_namespace, local_flow_name, flow_def)
        except RegistryError as exc:
            logger.warning(
                "Executable markdown agent flow '%s.%s' from '%s' collides with an existing registration: %s",
                target_namespace,
                local_flow_name,
                agent_path,
                exc,
            )

    def _is_self_contained_agent_candidate(self, definition: Dict[str, Any]) -> bool:
        return any(definition.get(key) for key in _SELF_CONTAINED_AGENT_FLOW_KEYS)

    def _build_flow_definition_from_agent_markdown(
        self,
        *,
        definition: Dict[str, Any],
        flow_name: str,
        authoring_namespace: str,
        registration_root: Path,
        agent_path: Path,
        target_source: str,
    ) -> tuple[FlowDefinition, str, str]:
        if "." in flow_name:
            target_namespace, local_flow_name = flow_name.split(".", 1)
        else:
            target_namespace, local_flow_name = authoring_namespace, flow_name

        system_prompt, prompt_sources = resolve_prompt_bundle(
            definition,
            base_dir=agent_path.parent,
            inline_keys=("inline_prompt", "prompt", "system_prompt"),
            file_keys=("system_prompt_file", "prompt_file"),
            files_key="prompt_files",
            default_files=[],
            fallback_dirs=self._workspace_prompt_fallback_dirs(),
            prompt_registry=self.prompts,
            context_namespace=authoring_namespace,
        )
        llm_profile = definition.get("llm_profile")
        tools = coerce_str_list(definition.get("tools"))
        handoff_agents = coerce_str_list(definition.get("handoff_agents"))
        composite_agents = coerce_str_list(definition.get("composite_agents"))
        execution_mode = str(
            definition.get("execution_mode")
            or ("vm" if any(definition.get(key) for key in ("vm_source", "vm_file", "vm_module", "vm_files", "vm_modules")) else "llm")
        ).strip() or "llm"
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

        flow_instance = None
        if execution_mode.lower() != "vm":
            flow_instance = self._load_agent_flow(
                module_ref=definition.get("module"),
                entry_fn_name=definition.get("entry_fn"),
                namespace_root=agent_path.parent,
                agent_name=local_flow_name,
                namespace_name=authoring_namespace,
            )
            if flow_instance is None and any(definition.get(k) for k in ("nodes", "mermaid", "graph", "dot")):
                raise ValueError("Graph flows no longer supported. Use StackVM instead.")

        flow_def = FlowDefinition(
            name=local_flow_name,
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
            vm_entry=str(definition["vm_entry"]).strip() if definition.get("vm_entry") else None,
            vm_module=str(definition["vm_module"]).strip() if definition.get("vm_module") else None,
            vm_modules=coerce_str_list(definition.get("vm_modules")),
            vm_module_prefixes=_coerce_str_dict(definition.get("vm_module_prefixes")),
            vm_file=str(definition["vm_file"]).strip() if definition.get("vm_file") else None,
            vm_files=coerce_str_list(definition.get("vm_files")),
            vm_source=str(definition["vm_source"]).strip() if definition.get("vm_source") else None,
            metadata={
                **dict(definition.get("metadata") or {}),
                "namespace": authoring_namespace,
                "namespace_root": str(registration_root),
                "markdown_path": str(agent_path.resolve()),
                "agent_markdown_path": str(agent_path.resolve()),
                "agent_source": target_source,
            },
        )
        return flow_def, target_namespace, local_flow_name

    def _apply_adjacent_markdown_resource_defaults(
        self,
        *,
        definition: Dict[str, Any],
        registration_root: Path,
        markdown_path: Path,
    ) -> None:
        base_name = self._markdown_program_basename(markdown_path)
        if not base_name:
            return

        prompt_keys = ("prompt_file", "system_prompt_file", "prompt_files")
        if not any(definition.get(key) for key in prompt_keys):
            prompt_candidate = markdown_path.with_name(f"{base_name}.prompt.md")
            if prompt_candidate.is_file() and not self._catalog_resource_is_ignored(registration_root, prompt_candidate):
                definition["prompt_files"] = [prompt_candidate.name]

        if not coerce_str_list(definition.get("tool_files")):
            tool_candidate = markdown_path.with_name(f"{base_name}{TOOL_MODULE_SUFFIX}")
            if tool_candidate.is_file() and not self._catalog_resource_is_ignored(registration_root, tool_candidate):
                definition["tool_files"] = [tool_candidate.name]

    def _markdown_program_basename(self, markdown_path: Path) -> str:
        name = Path(markdown_path).name
        if name.endswith(".agent.md"):
            return name[: -len(".agent.md")]
        if name.endswith(".md"):
            return name[: -len(".md")]
        return Path(markdown_path).stem

    def _flat_resource_asset_name(self, asset_path: Path, *, suffix: str) -> str:
        name = asset_path.name
        if not name.endswith(suffix):
            return ""
        return name[: -len(suffix)]

    def _validate_loaded_flow_references(self) -> None:
        for qualified_flow_name, flow_def in self.flows.items():
            metadata = flow_def.metadata or {}
            context_namespace = metadata.get("namespace")
            flow_def.tools = self._qualify_existing_tool_refs(
                flow_def.tools,
                owner_name=qualified_flow_name,
                field_name="tools",
                context_namespace=context_namespace,
            )
            flow_def.handoff_agents = self._qualify_existing_flow_refs(
                flow_def.handoff_agents,
                owner_name=qualified_flow_name,
                field_name="handoff_agents",
                context_namespace=context_namespace,
            )
            flow_def.composite_agents = self._qualify_existing_flow_refs(
                flow_def.composite_agents,
                owner_name=qualified_flow_name,
                field_name="composite_agents",
                context_namespace=context_namespace,
            )

            default_agent = flow_def.default_agent_profile
            if default_agent is None:
                continue
            if default_agent.tools is not None:
                default_agent.tools = self._qualify_existing_tool_refs(
                    default_agent.tools,
                    owner_name=f"{qualified_flow_name}.default_agent",
                    field_name="tools",
                    context_namespace=context_namespace,
                )
            default_agent.extra_prompts = self._filter_existing_prompt_refs(
                default_agent.extra_prompts,
                owner_name=f"{qualified_flow_name}.default_agent",
                field_name="extra_prompts",
                context_namespace=context_namespace,
            )

    def _qualify_existing_tool_refs(
        self,
        refs: List[str],
        *,
        owner_name: str,
        field_name: str,
        context_namespace: str | None,
    ) -> List[str]:
        qualified: List[str] = []
        for ref in refs:
            candidate = str(ref or "").strip()
            if not candidate:
                continue
            if candidate == "*":
                return ["*"]
            try:
                resolved = self.tools.qualify(candidate, context_namespace=context_namespace)
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
        context_namespace: str | None,
    ) -> List[str]:
        qualified: List[str] = []
        for ref in refs:
            candidate = str(ref or "").strip()
            if not candidate:
                continue
            try:
                resolved = self.flows.qualify(candidate, context_namespace=context_namespace)
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
        context_namespace: str | None,
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
                    context_namespace=context_namespace,
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

    def _workspace_prompt_roots(self, resource_root_path: Path) -> list[Path]:
        prompts_root = resource_root_path / "prompts"
        return [prompts_root] if prompts_root.is_dir() else []

    def _workspace_tool_roots(self, resource_root_path: Path) -> list[tuple[Path, str | None]]:
        roots: list[tuple[Path, str | None]] = []
        seen: set[Path] = set()

        tools_root = resource_root_path / "tools"
        if tools_root.is_dir():
            resolved = tools_root.resolve()
            seen.add(resolved)
            roots.append((tools_root, None))

        for path in sorted(candidate for candidate in resource_root_path.iterdir() if candidate.is_dir()):
            if not path.name.startswith("tool."):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            roots.append((path, path.name[len("tool."):].strip() or None))

        return roots

    def _prefix_asset_name(self, prefix: str | None, asset_name: str) -> str:
        if not prefix:
            return asset_name
        if not asset_name:
            return prefix
        return f"{prefix}.{asset_name}"

    def _iter_workspace_hook_files(self, resource_root: ResourceRoot) -> list[tuple[Path, str | None]]:
        files: list[tuple[Path, str | None]] = []
        seen: set[Path] = set()

        for path in sorted(resource_root.path.glob("*.hook.yaml")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append((path, None))

        for path in sorted(resource_root.path.glob("*.hook.md")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append((path, None))

        hook_roots: list[tuple[Path, str | None]] = []
        hooks_root = resource_root.path / "hooks"
        if hooks_root.is_dir():
            hook_roots.append((hooks_root, None))
        for path in sorted(candidate for candidate in resource_root.path.iterdir() if candidate.is_dir()):
            if path.name.startswith("hook."):
                hook_roots.append((path, path.name[len("hook."):].strip() or None))

        for hook_root, prefix in hook_roots:
            for path in sorted(candidate for candidate in hook_root.rglob("*.hook.yaml") if candidate.is_file()):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                asset_name = self._workspace_asset_name(hook_root, path, suffix=".hook.yaml")
                files.append((path, self._prefix_asset_name(prefix, asset_name)))
            for path in sorted(candidate for candidate in hook_root.rglob("*.hook.md") if candidate.is_file()):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                asset_name = self._workspace_asset_name(hook_root, path, suffix=".hook.md")
                files.append((path, self._prefix_asset_name(prefix, asset_name)))

        return files

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
        if raw_value is not None and self._is_explicit_workspace_tool_candidate(module, raw_value):
            return raw_value
        return None

    def _is_explicit_workspace_tool_candidate(self, module: types.ModuleType, value: Any) -> bool:
        if self._is_workspace_tool_candidate(module, value):
            return True
        if inspect.isfunction(value):
            return True
        if isinstance(value, type) and issubclass(value, BaseTool) and value is not BaseTool:
            return True
        return isinstance(value, BaseTool)

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

    def _register_flow_definition(
        self,
        flow_name: str,
        definition: Dict[str, Any],
        namespace_name: str,
        namespace_root: Path,
    ) -> None:
        definition = self._resolve_markdown_flow_definition(
            flow_name=flow_name,
            definition=definition,
            namespace_name=namespace_name,
            namespace_root=namespace_root,
        )
        if not definition:
            return
        source_dir = namespace_root
        markdown_path = (definition.get("metadata") or {}).get("markdown_path")
        if isinstance(markdown_path, str) and markdown_path.strip():
            source_dir = Path(markdown_path).resolve().parent
            self._apply_adjacent_markdown_resource_defaults(
                definition=definition,
                registration_root=namespace_root,
                markdown_path=Path(markdown_path),
            )
        self._load_flow_definition_tool_files(
            definition=definition,
            namespace_name=namespace_name,
            registration_root=namespace_root,
            source_dir=source_dir,
            owner_name=f"{namespace_name}.{flow_name}",
        )

        llm_profile = definition.get("llm_profile")
        tools = definition.get("tools", [])
        if not tools and definition.get("allowed_tools"):
            tools = definition.get("allowed_tools", [])
        handoff_agents = definition.get("handoff_agents", [])

        if not isinstance(tools, list):
            tools = []
        if not isinstance(handoff_agents, list):
            handoff_agents = []

        raw_mode = str(
            definition.get("execution_mode")
            or definition.get("mode")
            or ("vm" if any(definition.get(key) for key in ("vm_source", "vm_file", "vm_module", "vm_files", "vm_modules")) else "llm")
        ).strip().lower()
        if raw_mode in {"node", "llm"}:
            execution_mode = "llm"
        elif raw_mode in {"deterministic", "python"}:
            execution_mode = "deterministic"
        elif raw_mode in {"composite"}:
            execution_mode = "composite"
        elif raw_mode in {"vm", "stackvm"}:
            execution_mode = "vm"
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

        system_prompt, prompt_sources = resolve_prompt_bundle(
            definition,
            base_dir=namespace_root,
            inline_keys=("system_prompt", "prompt"),
            file_keys=("system_prompt_file", "prompt_file"),
            files_key="prompt_files",
            default_files=[],
            fallback_dirs=self._workspace_prompt_fallback_dirs(),
            prompt_registry=self.prompts,
            context_namespace=namespace_name,
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

        flow_instance = None
        if execution_mode != "vm":
            flow_instance = self._load_agent_flow(
                module_ref=definition.get("module"),
                entry_fn_name=definition.get("entry_fn"),
                namespace_root=namespace_root,
                agent_name=flow_name,
                namespace_name=namespace_name,
            )
            if flow_instance is None and any(definition.get(k) for k in ("nodes", "mermaid", "graph", "dot")):
                raise ValueError("Graph flows no longer supported. Use StackVM instead.")

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
            vm_entry=str(definition["vm_entry"]).strip() if definition.get("vm_entry") else None,
            vm_module=str(definition["vm_module"]).strip() if definition.get("vm_module") else None,
            vm_modules=coerce_str_list(definition.get("vm_modules")),
            vm_module_prefixes=_coerce_str_dict(definition.get("vm_module_prefixes")),
            vm_file=str(definition["vm_file"]).strip() if definition.get("vm_file") else None,
            vm_files=coerce_str_list(definition.get("vm_files")),
            vm_source=str(definition["vm_source"]).strip() if definition.get("vm_source") else None,
            metadata={
                **dict(definition.get("metadata") or {}),
                "namespace": namespace_name,
                "namespace_root": str(namespace_root),
            },
        )
        raw_dap = definition.get("default_agent")
        if isinstance(raw_dap, dict):
            qualified_name = f"{namespace_name}.{flow_name}"
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
                source="namespace",
                source_path=None,
            )
            flow_def.default_agent = dap_profile
            logger.debug(
                "Namespace '%s' flow '%s': loaded default_agent '%s'.",
                namespace_name,
                flow_name,
                dap_name,
            )

        try:
            self.flows.register(namespace_name, flow_name, flow_def)
        except RegistryError as exc:
            logger.error(
                "Namespace '%s' flow '%s' registry collision: %s — skipping.",
                namespace_name,
                flow_name,
                exc,
            )

    def _resolve_markdown_flow_definition(
        self,
        *,
        flow_name: str,
        definition: Dict[str, Any],
        namespace_name: str,
        namespace_root: Path,
    ) -> Dict[str, Any]:
        markdown_ref = self._markdown_asset_reference(definition)
        if markdown_ref is None:
            return definition

        markdown_path = (namespace_root / markdown_ref).resolve()
        try:
            document = load_markdown_asset_document(
                markdown_path,
                fallback_dirs=self._workspace_prompt_fallback_dirs(),
                prompt_registry=self.prompts,
                context_namespace=namespace_name,
            )
            compiled = compile_markdown_flow_definition(document, default_name=flow_name)
        except Exception as exc:
            logger.error(
                "Namespace '%s' flow '%s': failed to load markdown definition '%s': %s",
                namespace_name,
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
        namespace_root: Path,
        agent_name: str,
        namespace_name: str,
    ) -> Any:
        """Load a PocketFlow Flow from a Markdown module+entry_fn declaration.

        Returns the Flow instance if the factory is found and callable, ``None`` otherwise.
        On any exception, logs at ERROR and returns ``None`` (agent still registers
        without a flow_instance, using the default LLM path).
        """
        if not module_ref or not entry_fn_name:
            return None
        try:
            file_path = (namespace_root / module_ref).resolve()
            module = self._load_module_from_file(file_path)
            factory = getattr(module, entry_fn_name, None)
            if not callable(factory):
                logger.error(
                    "Namespace '%s' agent '%s': entry_fn '%s' not found or not callable in '%s'.",
                    namespace_name,
                    agent_name,
                    entry_fn_name,
                    file_path,
                )
                return None
            flow = factory()
            logger.debug(
                "Namespace '%s' agent '%s': flow_instance loaded from '%s:%s'.",
                namespace_name,
                agent_name,
                module_ref,
                entry_fn_name,
            )
            return flow
        except Exception as exc:
            logger.error(
                "Namespace '%s' agent '%s': failed to load flow from '%s:%s': %s",
                namespace_name,
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
        return tuple(dict.fromkeys(fallback_dirs))

    def _workspace_namespace_prompt_fallback_dirs(self, namespace_root: Path) -> tuple[Path, ...]:
        fallback_dirs = [namespace_root, *self._workspace_prompt_fallback_dirs()]
        return tuple(dict.fromkeys(fallback_dirs))

    def _reference_is_ignored(
        self,
        reference: Any,
        namespace_root: Path,
    ) -> bool:
        if not isinstance(reference, str):
            return False

        candidate = reference.strip()
        if not candidate or ":" not in candidate:
            return False

        path_part, _ = candidate.split(":", 1)
        file_path = (namespace_root / path_part).resolve()
        return self._catalog_resource_is_ignored(namespace_root, file_path)

    def _flow_definition_is_ignored(
        self,
        definition: Dict[str, Any],
        namespace_root: Path,
    ) -> bool:
        module_ref = definition.get("module")
        if isinstance(module_ref, str) and module_ref.strip():
            module_path = (namespace_root / module_ref).resolve()
            if self._catalog_resource_is_ignored(namespace_root, module_path):
                return True

        prompt_file = definition.get("prompt_file") or definition.get("system_prompt_file")
        if isinstance(prompt_file, str) and prompt_file.strip():
            prompt_path = (namespace_root / prompt_file).resolve()
            if self._catalog_resource_is_ignored(namespace_root, prompt_path):
                return True

        prompt_files = definition.get("prompt_files")
        if isinstance(prompt_files, list):
            for prompt_ref in prompt_files:
                if not isinstance(prompt_ref, str) or not prompt_ref.strip():
                    continue
                prompt_path = (namespace_root / prompt_ref).resolve()
                if self._catalog_resource_is_ignored(namespace_root, prompt_path):
                    return True

        return False

    def _catalog_root_is_ignored(self, namespace_root: Path) -> bool:
        resolved = namespace_root.resolve()
        containing_root = resource_root_for_path(resolved, self._resource_roots)
        if containing_root is not None:
            return self._resource_root_filter(containing_root).ignores(resolved, is_dir=True)
        return self._global_catalog_filter.ignores_relative(Path(resolved.name), is_dir=True)

    def _catalog_resource_is_ignored(self, namespace_root: Path, resource_path: Path) -> bool:
        resolved_namespace_root = namespace_root.resolve()
        resolved_resource = resource_path.resolve()
        containing_root = resource_root_for_path(resolved_namespace_root, self._resource_roots)
        if containing_root is not None:
            return self._resource_root_filter(containing_root).ignores(
                resolved_resource,
                is_dir=resolved_resource.is_dir(),
            )
        try:
            relative = resolved_resource.relative_to(resolved_namespace_root)
        except ValueError:
            return False
        return self._global_catalog_filter.ignores_relative(
            Path(resolved_namespace_root.name) / relative,
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
        return (resource_root_namespace(resource_root),)

    def _is_resource_root_namespace_pack_asset(self, root: Path, asset_path: Path) -> bool:
        prefixes = self._resource_root_namespace_packs.get(root.resolve())
        if not prefixes:
            return False
        name = asset_path.name
        if name.endswith(".agent.yaml"):
            return False
        first_segment = name.split(".", 1)[0].strip()
        if first_segment not in prefixes:
            return False
        return name.count(".") >= 2

    def _load_reference(self, reference: Any, namespace_root: Path) -> Any:
        if not isinstance(reference, str):
            return reference

        candidate = reference.strip()
        if not candidate:
            raise ValueError("Empty reference string.")

        if ":" in candidate:
            path_part, object_name = candidate.split(":", 1)
            file_path = (namespace_root / path_part).resolve()
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
        return f"pocketcode_dynamic_resource_{abs(hash(token))}"

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
