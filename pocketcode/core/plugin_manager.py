from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

from pocketcode.core.interfaces import Plugin, PluginContext
from pocketcode.core.prompt_loader import coerce_str_list, resolve_prompt_bundle
from pocketcode.core.runtime_models import AgentDefinition

logger = logging.getLogger(__name__)


class PluginManager:
    def __init__(self, config: Dict[str, Any], workspace_root: str | Path):
        self._config = config
        self._workspace_root = Path(workspace_root).resolve()

        self.tools: Dict[str, Any] = {}
        self.agents: Dict[str, AgentDefinition] = {}
        self.llm_profiles: Dict[str, Dict[str, Any]] = {}
        self.plugin_roots: Dict[str, Path] = {}
        self.plugins: Dict[str, Plugin] = {}

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def clear(self) -> None:
        self.tools.clear()
        self.agents.clear()
        self.llm_profiles.clear()
        self.plugin_roots.clear()
        self.plugins.clear()

    def load(self) -> None:
        self.clear()

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

        logger.info(
            "Plugin load complete. plugins=%d, tools=%d, agents=%d, llm_profiles=%d",
            len(self.plugin_roots),
            len(self.tools),
            len(self.agents),
            len(self.llm_profiles),
        )

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
                if tool_name in self.tools:
                    logger.warning(f"Plugin '{plugin_name}' tool '{tool_name}' collides with existing tool. Overwriting.")
                self.tools[tool_name] = tool
            
            # Register agents (Flows)
            for agent_name, flow in plugin.agents.items():
                self.agents[agent_name] = AgentDefinition(
                    name=agent_name,
                    description=plugin.description or f"Programmatic agent from {plugin_name}",
                    is_programmatic=True,
                    flow_instance=flow,
                    metadata={
                        "plugin_name": plugin_name,
                        "plugin_root": str(plugin_root),
                        "version": plugin.version,
                        "author": plugin.author
                    }
                )
                
            # Register LLM profiles from metadata if present
            if "llm_profiles" in plugin.metadata:
                self._load_plugin_llm_profiles(plugin_name, plugin.metadata)
                
            return True
            
        except Exception as exc:
            logger.error(f"Factory load failed for {plugin_root}: {exc}", exc_info=True)
            return False

    def _load_module_from_file(self, file_path: Path) -> Any:
        module_name = f"pocketcode_dynamic_plugin_{abs(hash(str(file_path)))}"

        if module_name in sys.modules:
            return sys.modules[module_name]
        
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if not spec or not spec.loader:
            raise ImportError(f"Unable to create import spec for {file_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

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

            # Check if current base_path itself is a plugin (has __init__.py, agent.yaml, or plugin.yaml)
            if (base_path / "__init__.py").is_file() or (base_path / "agent.yaml").is_file() or (base_path / "plugin.yaml").is_file():
                resolved = base_path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    yield resolved
                continue

            # Otherwise, iterate through children
            for child in sorted(base_path.iterdir()):
                if child.is_dir() and ((child / "__init__.py").is_file() or (child / "agent.yaml").is_file() or (child / "plugin.yaml").is_file()):
                    resolved = child.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        yield resolved

    def _load_plugin(self, plugin_root: Path) -> None:
        if (plugin_root / "agent.yaml").is_file():
            self._load_agent_plugin(plugin_root)
            return

        manifest_path = plugin_root / "plugin.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(manifest, dict):
            raise ValueError(f"Plugin manifest must be a YAML object: {manifest_path}")

        plugin_name = str(manifest.get("name") or plugin_root.name)
        self.plugin_roots[plugin_name] = plugin_root

        logger.info("Loading legacy plugin '%s' from %s", plugin_name, plugin_root)

        self._load_plugin_llm_profiles(plugin_name, manifest)
        self._load_plugin_tools(plugin_name, plugin_root, manifest)
        self._load_plugin_agents(plugin_name, plugin_root, manifest)

        # Explicitly ignore removed legacy sections.
        for legacy_key in ("components", "workflows", "flows", "modes"):
            if legacy_key in manifest:
                logger.warning(
                    "Plugin '%s' contains legacy '%s' section; it is ignored in agent-only runtime.",
                    plugin_name,
                    legacy_key,
                )

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
                    loaded_tool = self._load_reference(tool_ref, plugin_root)
                    self.tools[tool_id] = loaded_tool
                    agent_tools.append(tool_id)
                except Exception as exc:
                    logger.error("Failed to load tool '%s' for agent '%s': %s", tool_id, agent_name, exc)

        self.agents[agent_name] = AgentDefinition(
            name=agent_name,
            description=str(manifest.get("description", "")),
            tools=agent_tools,
            system_prompt=system_prompt,
            metadata={
                "plugin": agent_name,
                "plugin_root": str(plugin_root),
                "version": manifest.get("version"),
                "author": manifest.get("author")
            }
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

    def _load_plugin_agents(self, plugin_name: str, plugin_root: Path, manifest: Dict[str, Any]) -> None:
        agents_section = manifest.get("agents", {})
        if not isinstance(agents_section, dict):
            logger.warning("Plugin '%s' agents section is not a mapping. Skipping.", plugin_name)
            return

        for agent_name, raw_definition in agents_section.items():
            definition = raw_definition if isinstance(raw_definition, dict) else {}
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

        self.agents[agent_name] = AgentDefinition(
            name=agent_name,
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
            metadata={
                "plugin": plugin_name,
                "plugin_root": str(plugin_root),
            },
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
