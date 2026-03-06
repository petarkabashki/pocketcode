from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pocketcode.core.agent_profile_manager import AgentProfileManager
from pocketcode.core.agent_runtime import AgentRuntime
from pocketcode.core.llm_router import LlmRouter
from pocketcode.core.plugin_manager import PluginManager
from pocketcode.core.run_handle import RunHandle
from pocketcode.core.tool_runtime import ToolRuntime

logger = logging.getLogger(__name__)


class PocketCodeEngine:
    def __init__(self, config: Dict[str, Any], workspace_root: str | Path):
        self._config = config
        self._workspace_root = Path(workspace_root).resolve()
        self._runtime_config = config.get("runtime", {}) if isinstance(config, dict) else {}
        self._llm_config = config.get("llm", {}) if isinstance(config, dict) else {}
        if not isinstance(self._llm_config, dict):
            self._llm_config = {}
        self._tool_confirmation_config = self._build_tool_confirmation_config()

        self._plugins = PluginManager(config=config, workspace_root=self._workspace_root)
        self._plugins.load()

        # T011: instantiate AgentProfileManager after plugins are loaded.
        self._agent_profile_manager = AgentProfileManager(self._workspace_root)
        self._agent_profile_manager.load(dict(self._plugins.agents))
        self.active_agent_profile = None  # type: ignore[assignment]  # AgentProfile | None

        self._llm_router = LlmRouter(config=config, plugin_llm_profiles=self._plugins.llm_profiles)
        self._tool_runtime = ToolRuntime(
            tools=self._plugins.tools,
            require_confirmation=bool(self._runtime_config.get("require_tool_confirmation", True)),
            auto_approved_tools=list(self._runtime_config.get("auto_approved_tools", [])),
            confirmation_config=self._tool_confirmation_config,
        )
        self._agent_runtime = AgentRuntime(
            plugin_manager=self._plugins,
            llm_router=self._llm_router,
            tool_runtime=self._tool_runtime,
            runtime_config=self._runtime_config,
        )
        self._agent_tools_cache: Dict[str, List[str]] = {}

        self.default_llm_profile = (
            self._llm_config.get("default_profile")
            or self._llm_router.default_profile_name
        )
        self.config_llm_overrides = self._build_llm_overrides_config()

        self.current_agent = self._runtime_config.get("default_agent")
        self.global_llm_override = None  # type: ignore[assignment]
        self.agent_llm_overrides: Dict[str, str] = {}
        self.handoff_llm_overrides: Dict[str, str] = {}
        self.auto_confirm_tools = bool(self._runtime_config.get("auto_confirm_tools", False))
        self.session_confirmation_overrides: Dict[str, Any] = {
            "default_policy": None,
            "tool_policies": {},
            "agent_policies": {},
        }
        self.last_run_summary: Dict[str, Any] = {
            "agent_path": [],
            "current_agent": self.current_agent,
            "current_llm_profile": None,
            "current_llm_model": None,
            "llm_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "llm_cost_usd": 0.0,
            "context_stats": {"files": 0, "folders": 0, "urls": 0, "snippets": 0, "snippet_chars": 0},
        }

        self._validate_current_selections()

    def reload(self) -> None:
        self._plugins.load()
        # T014: reload APM after plugins reload.
        self._agent_profile_manager.reload(dict(self._plugins.agents))
        # Re-apply active profile by name if it still exists; else fall back to
        # the current agent's default profile.
        if self.active_agent_profile is not None:
            still_exists = self._agent_profile_manager.get(self.active_agent_profile.name)
            if still_exists is not None:
                self.active_agent_profile = still_exists
            elif self.current_agent:
                self._activate_default_profile_for(self.current_agent)
            else:
                self.active_agent_profile = None
        self._llm_router = LlmRouter(config=self._config, plugin_llm_profiles=self._plugins.llm_profiles)
        self.config_llm_overrides = self._build_llm_overrides_config()
        self._tool_confirmation_config = self._build_tool_confirmation_config()
        self._tool_runtime = ToolRuntime(
            tools=self._plugins.tools,
            require_confirmation=bool(self._runtime_config.get("require_tool_confirmation", True)),
            auto_approved_tools=list(self._runtime_config.get("auto_approved_tools", [])),
            confirmation_config=self._tool_confirmation_config,
        )
        self._agent_runtime = AgentRuntime(
            plugin_manager=self._plugins,
            llm_router=self._llm_router,
            tool_runtime=self._tool_runtime,
            runtime_config=self._runtime_config,
        )
        self._agent_tools_cache = {}
        self._validate_current_selections()

    def _validate_current_selections(self) -> None:
        if self.current_agent and self.current_agent not in self._plugins.agents:
            self.current_agent = None

        invalid_agent_overrides = [
            agent_name
            for agent_name in self.agent_llm_overrides.keys()
            if agent_name not in self._plugins.agents
        ]
        for agent_name in invalid_agent_overrides:
            self.agent_llm_overrides.pop(agent_name, None)

        invalid_handoff_overrides = []
        for handoff_key in self.handoff_llm_overrides.keys():
            source, _, target = handoff_key.partition("->")
            if source not in self._plugins.agents or target not in self._plugins.agents:
                invalid_handoff_overrides.append(handoff_key)
        for handoff_key in invalid_handoff_overrides:
            self.handoff_llm_overrides.pop(handoff_key, None)

    def list_agents(self) -> List[str]:
        return sorted(self._plugins.agents.keys())

    def list_llm_profiles(self) -> List[str]:
        return self._llm_router.list_profile_names()

    def get_current_agent(self):
        return self.current_agent

    def set_agent(self, agent_name: Optional[str]) -> None:
        if not agent_name:
            self.current_agent = None
            self.active_agent_profile = None
            return
        if agent_name not in self._plugins.agents:
            raise KeyError(f"Unknown agent '{agent_name}'.")
        self.current_agent = agent_name
        # T012: auto-activate the agent's default profile.
        self._activate_default_profile_for(agent_name)

    def set_active_agent_profile(self, name: Optional[str]) -> None:
        """Activate a named agent profile, or clear the active profile if name is None."""
        if name is None:
            self.active_agent_profile = None
            return
        profile = self._agent_profile_manager.get(name)
        if profile is None:
            available = [p.name for p in self._agent_profile_manager.list()]
            raise ValueError(
                f"Unknown agent profile '{name}'. "
                f"Available: {available}"
            )
        if profile.agent not in self._plugins.agents:
            raise ValueError(
                f"Agent profile '{name}' targets unknown agent '{profile.agent}'."
            )
        self.current_agent = profile.agent
        self.active_agent_profile = profile

    def list_agent_profiles(self, agent_name: Optional[str] = None) -> List[str]:
        """Return known agent profile names, optionally filtered by target agent."""
        profiles = self._agent_profile_manager.list()
        if agent_name:
            profiles = [profile for profile in profiles if profile.agent == agent_name]
        return [p.name for p in profiles]

    def get_agent_profile(self, name: Optional[str] = None) -> Any:
        """Return a named agent profile, or the active one when *name* is None."""
        if name is None:
            return self.active_agent_profile
        return self._agent_profile_manager.get(name)

    def clone_agent_profile(self, src_name: str, new_name: str) -> Any:
        """Clone an agent profile and return the new workspace-backed profile."""
        return self._agent_profile_manager.clone(src_name, new_name)

    def update_agent_profile(
        self,
        name: str,
        *,
        llm_profile: Optional[str],
        tools: Optional[List[str]],
        extra_prompts: List[str],
        tool_confirmation_default: Optional[str],
        tool_confirmation_overrides: Optional[Dict[str, Optional[str]]] = None,
    ) -> Any:
        """Persist updates to a workspace-backed agent profile and refresh runtime state."""
        profile = self._agent_profile_manager.get(name)
        if profile is None:
            raise ValueError(f"Unknown agent profile '{name}'.")
        if profile.source != "workspace" or profile.source_path is None:
            raise ValueError(
                f"Agent profile '{name}' is not workspace-backed. Clone it before editing."
            )
        if llm_profile:
            self._llm_router.resolve_profile_config(llm_profile)

        confirmation = dict(profile.tool_confirmation or {})
        if tool_confirmation_default is None:
            confirmation.pop("default", None)
        else:
            confirmation["default"] = self._normalize_confirmation_policy(tool_confirmation_default)
        if tool_confirmation_overrides is None:
            raw_overrides = dict(confirmation.get("overrides", {}))
        else:
            raw_overrides = dict(tool_confirmation_overrides)

        normalized_overrides = {
            str(tool_name): normalized
            for tool_name, policy in raw_overrides.items()
            if (normalized := self._normalize_confirmation_policy(policy)) is not None
        }
        if normalized_overrides:
            confirmation["overrides"] = normalized_overrides
        elif "overrides" in confirmation:
            confirmation.pop("overrides", None)

        updated = dataclasses.replace(
            profile,
            llm_profile=llm_profile or None,
            tools=list(tools) if tools is not None else None,
            extra_prompts=list(extra_prompts),
            tool_confirmation=confirmation,
        )
        self._agent_profile_manager.save(updated)
        self._agent_profile_manager.reload(dict(self._plugins.agents))
        refreshed = self._agent_profile_manager.get(name)
        if refreshed is not None and self.active_agent_profile and self.active_agent_profile.name == name:
            self.active_agent_profile = refreshed
        return refreshed

    def list_tools_for_agent(
        self,
        agent_name: str,
        *,
        apply_active_profile: bool = False,
    ) -> List[str]:
        """Return tool names for an agent, optionally filtered by the active profile."""
        if agent_name not in self._plugins.agents:
            raise KeyError(f"Unknown agent '{agent_name}'.")
        if not apply_active_profile and agent_name in self._agent_tools_cache:
            return list(self._agent_tools_cache[agent_name])

        tool_names = list(self._plugins.resolve_tools_for_agent(agent_name))
        if apply_active_profile:
            active_profile = self.active_agent_profile
            if (
                active_profile is not None
                and active_profile.agent == agent_name
                and active_profile.tools is not None
            ):
                tool_names = [tool_name for tool_name in tool_names if tool_name in active_profile.tools]
        sorted_tool_names = sorted(tool_names)
        if not apply_active_profile:
            self._agent_tools_cache[agent_name] = list(sorted_tool_names)
        return sorted_tool_names

    def describe_agent(self, agent_name: Optional[str] = None) -> Dict[str, Any]:
        """Expose agent metadata for the control-oriented TUI."""
        target = agent_name or self.current_agent
        if not target:
            return {
                "name": None,
                "description": "",
                "execution_mode": "",
                "prompt_sources": [],
                "profiles": [],
                "tools": [],
            }
        definition = self._plugins.agents.get(target)
        if definition is None:
            raise KeyError(f"Unknown agent '{target}'.")
        return {
            "name": target,
            "description": definition.description,
            "execution_mode": definition.execution_mode,
            "prompt_sources": list(definition.prompt_sources),
            "profiles": self.list_agent_profiles(target),
            "tools": self.list_tools_for_agent(target),
        }

    def get_agent_prompt_sources(self, agent_name: Optional[str] = None) -> List[str]:
        """Return prompt source paths for the target agent."""
        target = agent_name or self.current_agent
        if not target:
            return []
        definition = self._plugins.agents.get(target)
        if definition is None:
            raise KeyError(f"Unknown agent '{target}'.")
        return list(definition.prompt_sources)

    def _activate_default_profile_for(self, agent_name: str) -> None:
        """Set active_agent_profile to the agent's default profile."""
        defn = self._plugins.agents.get(agent_name)
        if defn is None:
            return
        explicit = getattr(defn, "default_agent_profile", None)
        if explicit is not None:
            default_name = explicit.name
        else:
            default_name = agent_name  # synthesised profile is named after the agent
        profile = self._agent_profile_manager.get(default_name)
        if profile is None:
            # Fall back to any profile whose agent field matches.
            for p in self._agent_profile_manager.list():
                if p.agent == agent_name:
                    profile = p
                    break
        self.active_agent_profile = profile

    def set_global_llm_override(self, profile_name: Optional[str]) -> None:
        if not profile_name:
            self.global_llm_override = None
            return
        self._llm_router.resolve_profile_config(profile_name)
        self.global_llm_override = profile_name

    def set_agent_llm_override(self, agent_name: str, profile_name: Optional[str]) -> None:
        if agent_name not in self._plugins.agents:
            raise KeyError(f"Unknown agent '{agent_name}'.")

        if not profile_name:
            self.agent_llm_overrides.pop(agent_name, None)
            return

        self._llm_router.resolve_profile_config(profile_name)
        self.agent_llm_overrides[agent_name] = profile_name

    def set_handoff_llm_override(
        self,
        source_agent: str,
        target_agent: str,
        profile_name: Optional[str],
    ) -> None:
        if source_agent not in self._plugins.agents:
            raise KeyError(f"Unknown source agent '{source_agent}'.")
        if target_agent not in self._plugins.agents:
            raise KeyError(f"Unknown target agent '{target_agent}'.")

        handoff_key = f"{source_agent}->{target_agent}"

        if not profile_name:
            self.handoff_llm_overrides.pop(handoff_key, None)
            return

        self._llm_router.resolve_profile_config(profile_name)
        self.handoff_llm_overrides[handoff_key] = str(profile_name)

    def describe_tools_for_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        if agent_name not in self._plugins.agents:
            raise KeyError(f"Unknown agent '{agent_name}'.")
        tool_names = self._plugins.resolve_tools_for_agent(agent_name)
        active_profile = self.active_agent_profile
        if active_profile is not None and active_profile.agent == agent_name and active_profile.tools is not None:
            tool_names = [tool_name for tool_name in tool_names if tool_name in active_profile.tools]
        return self._tool_runtime.describe_tools(tool_names)

    def start_request(
        self,
        user_input: str,
        cli_context: Dict[str, Any],
        *,
        bridge_user_input: bool = False,
    ) -> RunHandle:
        handle = RunHandle()
        shared_store = self._build_shared_store(
            user_input=user_input,
            cli_context=cli_context,
            event_handler=handle.emit,
            user_input_handler=handle.request_user_input if bridge_user_input else None,
        )

        def runner() -> None:
            try:
                handle.emit(
                    "run_started",
                    request=user_input,
                    agent=shared_store.get("active_agent") or "auto",
                )
                result = self._execute_request(shared_store=shared_store, cli_context=cli_context)
                handle.complete(result=result, summary=dict(self.last_run_summary))
            except Exception as exc:
                logger.error("Request processing failed: %s", exc, exc_info=True)
                handle.fail(exc)

        handle.start(runner)
        return handle

    def process_request(self, user_input: str, cli_context: Dict[str, Any]) -> str:
        return self.start_request(user_input=user_input, cli_context=cli_context).wait()

    def _build_shared_store(
        self,
        *,
        user_input: str,
        cli_context: Dict[str, Any],
        event_handler: Any = None,
        user_input_handler: Any = None,
    ) -> Dict[str, Any]:
        initial_agent = self.current_agent or self._runtime_config.get("default_agent")
        if not initial_agent:
            agents = self.list_agents()
            if agents:
                initial_agent = agents[0]

        shared_store: Dict[str, Any] = {
            "initial_request": user_input,
            "cli_context": self._copy_cli_context(cli_context),
            "formatted_cli_context": self._format_cli_context(cli_context),
            "active_agent": initial_agent,
            "default_llm_profile": self.default_llm_profile,
            "cli_llm_override": self.global_llm_override,
            "cli_agent_llm_overrides": dict(self.agent_llm_overrides),
            "cli_handoff_llm_overrides": dict(self.handoff_llm_overrides),
            "config_agent_llm_overrides": dict(self.config_llm_overrides.get("agents", {})),
            "config_handoff_llm_overrides": dict(self.config_llm_overrides.get("handoffs", {})),
            "auto_confirm_tools": self.auto_confirm_tools,
            "session_tool_confirmation": self._copy_session_confirmation_overrides(),
            # T013: inject active agent profile so AgentRuntime / ToolRuntime can read it.
            "active_agent_profile": self.active_agent_profile,
        }
        if callable(event_handler):
            shared_store["runtime_event_handler"] = event_handler
        if callable(user_input_handler):
            shared_store["user_input_handler"] = user_input_handler
        return shared_store

    def _execute_request(self, *, shared_store: Dict[str, Any], cli_context: Dict[str, Any]) -> str:
        self._agent_runtime.run(shared_store)

        if shared_store.get("active_agent"):
            self.current_agent = shared_store["active_agent"]

        self.last_run_summary = {
            "agent_path": self._build_agent_path(shared_store),
            "current_agent": shared_store.get("active_agent") or self.current_agent,
            "current_llm_profile": shared_store.get("last_llm_profile"),
            "current_llm_model": (
                shared_store.get("last_llm_generation", {}).get("model")
                if isinstance(shared_store.get("last_llm_generation"), dict)
                else None
            ),
            "llm_usage": dict(shared_store.get("llm_usage_totals", {}))
            if isinstance(shared_store.get("llm_usage_totals", {}), dict)
            else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "llm_cost_usd": float(shared_store.get("llm_cost_usd_total", 0.0)),
            "context_stats": self._build_context_stats(cli_context),
        }

        return str(shared_store.get("final_output") or shared_store.get("final_answer") or "No output generated.")

    def status(self) -> Dict[str, Any]:
        return {
            "agent": self.current_agent,
            "runtime_workflow": self._runtime_config.get("agent_runtime_workflow"),
            # T013: expose active agent profile name.
            "active_agent_profile": self.active_agent_profile.name if self.active_agent_profile else None,
            "global_llm_override": self.global_llm_override,
            "agent_llm_overrides": dict(self.agent_llm_overrides),
            "handoff_llm_overrides": dict(self.handoff_llm_overrides),
            "config_llm_overrides": dict(self.config_llm_overrides),
            "default_llm_profile": self.default_llm_profile,
            "tool_confirmation": self._tool_confirmation_config,
            "session_tool_confirmation_overrides": self._copy_session_confirmation_overrides(),
            "available_agents": self.list_agents(),
            "available_llm_profiles": self.list_llm_profiles(),
            "last_run_summary": dict(self.last_run_summary),
        }

    def set_session_confirmation_default(self, policy: Optional[str]) -> None:
        self.session_confirmation_overrides["default_policy"] = self._normalize_confirmation_policy(policy)

    def set_session_tool_confirmation(self, tool_name: str, policy: Optional[str]) -> None:
        self._set_policy_entry(self.session_confirmation_overrides["tool_policies"], tool_name, policy)

    def set_session_agent_confirmation(self, agent_name: str, policy: Optional[str]) -> None:
        agent_entry = self._get_or_create_session_agent_entry(agent_name)
        normalized = self._normalize_confirmation_policy(policy)
        if normalized is None:
            agent_entry.pop("default_policy", None)
        else:
            agent_entry["default_policy"] = normalized
        self._cleanup_session_agent_entry(agent_name)

    def set_session_agent_tool_confirmation(self, agent_name: str, tool_name: str, policy: Optional[str]) -> None:
        agent_entry = self._get_or_create_session_agent_entry(agent_name)
        self._set_policy_entry(agent_entry.setdefault("tool_policies", {}), tool_name, policy)
        self._cleanup_session_agent_entry(agent_name)

    def clear_session_confirmation_overrides(self) -> None:
        self.session_confirmation_overrides = {
            "default_policy": None,
            "tool_policies": {},
            "agent_policies": {},
        }

    def _copy_cli_context(self, cli_context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "files": sorted(list(cli_context.get("files", set()))),
            "folders": sorted(list(cli_context.get("folders", set()))),
            "urls": sorted(list(cli_context.get("urls", set()))),
            "snippets": dict(cli_context.get("snippets", {})),
        }

    def _build_tool_confirmation_config(self) -> Dict[str, Any]:
        section = self._runtime_config.get("tool_confirmation", {})
        if not isinstance(section, dict):
            section = {}
        return {
            "default_policy": section.get("default_policy"),
            "tool_policies": dict(section.get("tool_policies", {}))
            if isinstance(section.get("tool_policies", {}), dict)
            else {},
            "agent_policies": dict(section.get("agent_policies", {}))
            if isinstance(section.get("agent_policies", {}), dict)
            else {},
        }

    def _normalize_confirmation_policy(self, policy: Optional[str]) -> Optional[str]:
        if policy is None:
            return None
        normalized = str(policy).strip().lower()
        if normalized in {"allow", "confirm", "deny"}:
            return normalized
        raise ValueError(f"Invalid confirmation policy '{policy}'. Use allow|confirm|deny.")

    def _set_policy_entry(self, store: Dict[str, Any], key: str, policy: Optional[str]) -> None:
        normalized = self._normalize_confirmation_policy(policy)
        if normalized is None:
            store.pop(key, None)
        else:
            store[key] = normalized

    def _get_or_create_session_agent_entry(self, agent_name: str) -> Dict[str, Any]:
        agent_policies = self.session_confirmation_overrides.setdefault("agent_policies", {})
        entry = agent_policies.get(agent_name)
        if not isinstance(entry, dict):
            entry = {"tool_policies": {}}
            agent_policies[agent_name] = entry
        entry.setdefault("tool_policies", {})
        return entry

    def _cleanup_session_agent_entry(self, agent_name: str) -> None:
        agent_policies = self.session_confirmation_overrides.get("agent_policies", {})
        if not isinstance(agent_policies, dict):
            return
        entry = agent_policies.get(agent_name)
        if not isinstance(entry, dict):
            return
        tool_policies = entry.get("tool_policies", {})
        if not isinstance(tool_policies, dict):
            tool_policies = {}
            entry["tool_policies"] = tool_policies

        has_default = "default_policy" in entry and entry.get("default_policy") is not None
        if not has_default and not tool_policies:
            agent_policies.pop(agent_name, None)

    def _copy_session_confirmation_overrides(self) -> Dict[str, Any]:
        source = self.session_confirmation_overrides
        copied_agent_policies: Dict[str, Any] = {}
        raw_agent_policies = source.get("agent_policies", {})
        if isinstance(raw_agent_policies, dict):
            for agent_name, entry in raw_agent_policies.items():
                if not isinstance(entry, dict):
                    continue
                copied_agent_policies[agent_name] = {
                    "default_policy": entry.get("default_policy"),
                    "tool_policies": dict(entry.get("tool_policies", {}))
                    if isinstance(entry.get("tool_policies", {}), dict)
                    else {},
                }

        return {
            "default_policy": source.get("default_policy"),
            "tool_policies": dict(source.get("tool_policies", {}))
            if isinstance(source.get("tool_policies", {}), dict)
            else {},
            "agent_policies": copied_agent_policies,
        }

    def _build_llm_overrides_config(self) -> Dict[str, Dict[str, str]]:
        runtime_overrides = self._runtime_config.get("llm_overrides", {})
        if not isinstance(runtime_overrides, dict):
            return {"agents": {}, "handoffs": {}}

        agent_map: Dict[str, str] = {}
        raw_agents = runtime_overrides.get("agents", {})
        if isinstance(raw_agents, dict):
            for agent_name, profile_name in raw_agents.items():
                if isinstance(agent_name, str) and isinstance(profile_name, str):
                    agent_map[agent_name.strip()] = profile_name.strip()

        handoff_map: Dict[str, str] = {}
        raw_handoffs = runtime_overrides.get("handoffs", {})
        if isinstance(raw_handoffs, dict):
            for key, value in raw_handoffs.items():
                if isinstance(key, str) and isinstance(value, str):
                    handoff_map[key.strip()] = value.strip()
                    continue

                if isinstance(key, str) and isinstance(value, dict):
                    source_agent = key.strip()
                    for target_agent, profile_name in value.items():
                        if isinstance(target_agent, str) and isinstance(profile_name, str):
                            handoff_map[f"{source_agent}->{target_agent.strip()}"] = profile_name.strip()

        return {
            "agents": agent_map,
            "handoffs": handoff_map,
        }

    def _format_cli_context(self, cli_context_data: Dict[str, Any]) -> str:
        if not cli_context_data or not any(cli_context_data.values()):
            return "None provided."

        lines: List[str] = []
        files = cli_context_data.get("files") or set()
        folders = cli_context_data.get("folders") or set()
        urls = cli_context_data.get("urls") or set()
        snippets = cli_context_data.get("snippets") or {}

        if files:
            lines.append("Files:")
            lines.extend(f"- {item}" for item in sorted(list(files)))
        if folders:
            lines.append("Folders:")
            lines.extend(f"- {item}" for item in sorted(list(folders)))
        if urls:
            lines.append("URLs:")
            lines.extend(f"- {item}" for item in sorted(list(urls)))
        if snippets:
            lines.append("Snippets:")
            for name, content in sorted(snippets.items()):
                lines.append(f"- {name}: {content}")

        return "\n".join(lines) if lines else "None provided."

    def _build_context_stats(self, cli_context_data: Dict[str, Any]) -> Dict[str, int]:
        files = cli_context_data.get("files") or set()
        folders = cli_context_data.get("folders") or set()
        urls = cli_context_data.get("urls") or set()
        snippets = cli_context_data.get("snippets") or {}
        snippet_chars = 0
        if isinstance(snippets, dict):
            for value in snippets.values():
                if isinstance(value, str):
                    snippet_chars += len(value)
        return {
            "files": len(files),
            "folders": len(folders),
            "urls": len(urls),
            "snippets": len(snippets) if isinstance(snippets, dict) else 0,
            "snippet_chars": snippet_chars,
        }

    def _build_agent_path(self, shared_store: Dict[str, Any]) -> List[str]:
        trace = shared_store.get("agent_trace", [])
        if not isinstance(trace, list):
            trace = []

        ordered_agents: List[str] = []
        for item in trace:
            if not isinstance(item, dict):
                continue
            name = item.get("agent")
            if isinstance(name, str) and name and (not ordered_agents or ordered_agents[-1] != name):
                ordered_agents.append(name)

        handoff_history = shared_store.get("handoff_history", [])
        if isinstance(handoff_history, list):
            for handoff_agent in handoff_history:
                if isinstance(handoff_agent, str) and handoff_agent and (not ordered_agents or ordered_agents[-1] != handoff_agent):
                    ordered_agents.append(handoff_agent)

        return ordered_agents
