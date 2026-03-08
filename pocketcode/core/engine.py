from __future__ import annotations

import dataclasses
import logging
import copy
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import yaml

from pocketcode.core.agent_manager import AgentManager
from pocketcode.config.loader import WORKSPACE_SETTINGS_FILENAME
from pocketcode.core.markdown_profiles import ModeDefinition, ModeManager, SkillDefinition, SkillManager
from pocketcode.core.agent_runtime import AgentRuntime
from pocketcode.core.llm_router import LlmRouter
from pocketcode.core.namespace_registry import RegistryError
from pocketcode.core.plugin_manager import PluginManager
from pocketcode.core.run_handle import RunCancelledError, RunHandle
from pocketcode.core.runtime_models import AgentProfile
from pocketcode.core.session_manager import SessionManager
from pocketcode.core.tool_runtime import ToolRuntime
from pocketcode.core.workspace_llm_profile_manager import WorkspaceLlmProfileManager

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

        # T011: instantiate AgentManager after plugins are loaded.
        self._agent_profile_manager = AgentManager(self._workspace_root)
        self._agent_profile_manager.load(dict(self._plugins.agents))
        self._mode_manager = ModeManager(self._workspace_root)
        self._mode_manager.load()
        self._skill_manager = SkillManager(self._workspace_root)
        self._skill_manager.load()
        self._session_manager = SessionManager(self._workspace_root)
        self._workspace_llm_profile_manager = WorkspaceLlmProfileManager(self._workspace_root)
        self._workspace_llm_profile_manager.load()
        self.active_agent_profile = None  # type: ignore[assignment]  # AgentProfile | None
        self.active_mode: ModeDefinition | None = None
        self.enabled_skills = self._configured_enabled_skills()

        self._llm_router = LlmRouter(config=config, plugin_llm_profiles=self._merged_llm_profiles())
        self._tool_runtime = self._build_tool_runtime()
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

        self.current_agent = self._normalize_agent_name(self._runtime_config.get("default_agent"))
        self.global_llm_override = None  # type: ignore[assignment]
        self.agent_llm_overrides: Dict[str, str] = {}
        self.handoff_llm_overrides: Dict[str, str] = {}
        self.auto_confirm_tools = bool(self._runtime_config.get("auto_confirm_tools", False))
        self.session_confirmation_overrides: Dict[str, Any] = {
            "default_policy": None,
            "tool_policies": {},
            "agent_policies": {},
        }
        self.active_session_id: str | None = None
        self.active_session_title: str | None = None
        self.active_session_loaded_from_history = False
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
        self._restore_textual_selection_state()
        self._ensure_active_session()

    def reload(self) -> None:
        self._plugins.load()
        # T014: reload APM after plugins reload.
        self._agent_profile_manager.reload(dict(self._plugins.agents))
        self._mode_manager.load()
        self._skill_manager.load()
        # Re-apply active profile by name if it still exists; else fall back to
        # the current agent's default profile.
        if self.active_mode is not None:
            still_exists = self._mode_manager.get(self.active_mode.name)
            if still_exists is not None:
                self.set_mode(still_exists.name)
            else:
                self.active_mode = None
                if self.current_agent:
                    self._activate_default_profile_for(self.current_agent)
                else:
                    self.active_agent_profile = None
        elif self.active_agent_profile is not None:
            still_exists = self._agent_profile_manager.get(self.active_agent_profile.name)
            if still_exists is not None:
                self.active_agent_profile = self._apply_textual_profile_overrides(still_exists)
            elif self.current_agent:
                self._activate_default_profile_for(self.current_agent)
            else:
                self.active_agent_profile = None
        self._workspace_llm_profile_manager.load()
        self._llm_router = LlmRouter(config=self._config, plugin_llm_profiles=self._merged_llm_profiles())
        self.config_llm_overrides = self._build_llm_overrides_config()
        self._tool_confirmation_config = self._build_tool_confirmation_config()
        self.enabled_skills = [name for name in self.enabled_skills if self._skill_manager.get(name) is not None]
        self._refresh_runtime_components()
        self._agent_tools_cache = {}
        self._validate_current_selections()
        self._ensure_active_session()

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

        if self.active_mode is not None and self._mode_manager.get(self.active_mode.name) is None:
            self.active_mode = None

        self.enabled_skills = [
            skill_name
            for skill_name in self.enabled_skills
            if self._skill_manager.get(skill_name) is not None
        ]

    def list_agents(self) -> List[str]:
        """Backward-compatible alias for registered flow names."""
        return sorted(self._plugins.agents.keys())

    def list_flows(self) -> List[str]:
        return self.list_agents()

    def list_prompts(self) -> List[str]:
        return self._plugins.prompts.list_all()

    def list_llm_profiles(self) -> List[str]:
        return self._llm_router.list_profile_names()

    def get_llm_profile(self, name: Optional[str] = None) -> Any:
        target_name = str(name or self._selected_llm_profile() or "").strip()
        if not target_name:
            return None

        workspace_entry = self._workspace_llm_profile_manager.get(target_name)
        if workspace_entry is not None:
            return {
                "name": target_name,
                "source": "workspace",
                "source_path": workspace_entry.get("source_path"),
                "config": copy.deepcopy(workspace_entry.get("config", {})),
            }

        plugin_profile = self._plugins.llm_profiles.get(target_name)
        if isinstance(plugin_profile, dict):
            return {
                "name": target_name,
                "source": "plugin",
                "source_path": None,
                "config": copy.deepcopy(plugin_profile),
            }

        configured_profiles = self._llm_config.get("profiles", {})
        if isinstance(configured_profiles, dict):
            configured_profile = configured_profiles.get(target_name)
            if isinstance(configured_profile, dict):
                return {
                    "name": target_name,
                    "source": "config",
                    "source_path": self._workspace_root / "pocketcode.yml",
                    "config": copy.deepcopy(configured_profile),
                }

        resolved = self._llm_router.resolve_profile_config(target_name)
        return {
            "name": target_name,
            "source": "runtime",
            "source_path": None,
            "config": resolved,
        }

    def get_current_agent(self):
        """Backward-compatible alias for the current flow name."""
        return self.current_agent

    def get_current_flow(self):
        return self.get_current_agent()

    def get_system_settings(self) -> Dict[str, Any]:
        textual_config = self._runtime_config.get("textual", {})
        if not isinstance(textual_config, dict):
            textual_config = {}
        return {
            "theme_name": str(textual_config.get("theme_name") or "ocean"),
            "workspace_mode": str(textual_config.get("workspace_mode") or "balanced"),
            "default_agent": self._normalize_agent_name(self._runtime_config.get("default_agent")),
            "default_llm_profile": self._llm_config.get("default_profile"),
        }

    def get_textual_selection_settings(self) -> Dict[str, Any]:
        textual_config = self._runtime_config.get("textual", {})
        if not isinstance(textual_config, dict):
            textual_config = {}
        last_used = textual_config.get("last_used", {})
        if not isinstance(last_used, dict):
            last_used = {}
        agent_profiles = last_used.get("agent_profiles", {})
        if not isinstance(agent_profiles, dict):
            agent_profiles = {}
        default_skills = textual_config.get("default_skills", [])
        last_used_skills = last_used.get("skills", [])
        presets = textual_config.get("selection_presets", {})
        return {
            "default_skills": list(default_skills) if isinstance(default_skills, list) else [],
            "last_used_skills": list(last_used_skills) if isinstance(last_used_skills, list) else [],
            "agent_profiles": copy.deepcopy(agent_profiles),
            "active_profile": last_used.get("active_profile"),
            "active_mode": last_used.get("active_mode"),
            "global_llm_profile": last_used.get("global_llm_profile"),
            "session_confirmation_default": last_used.get("session_confirmation_default"),
            "auto_confirm_tools": bool(last_used.get("auto_confirm_tools", self.auto_confirm_tools)),
            "selection_presets": sorted(presets) if isinstance(presets, dict) else [],
        }

    def save_system_settings(
        self,
        *,
        theme_name: str,
        workspace_mode: str,
        default_agent: Optional[str],
        default_llm_profile: Optional[str],
    ) -> Path:
        normalized_default_agent = self._normalize_agent_name(default_agent)
        if normalized_default_agent:
            if normalized_default_agent not in self._plugins.agents:
                raise KeyError(f"Unknown agent '{default_agent}'.")
        if default_llm_profile:
            self._llm_router.resolve_profile_config(default_llm_profile)

        runtime_section = self._config.setdefault("runtime", {})
        if not isinstance(runtime_section, dict):
            runtime_section = {}
            self._config["runtime"] = runtime_section
        llm_section = self._config.setdefault("llm", {})
        if not isinstance(llm_section, dict):
            llm_section = {}
            self._config["llm"] = llm_section

        if normalized_default_agent:
            runtime_section["default_agent"] = str(normalized_default_agent)
        else:
            runtime_section.pop("default_agent", None)

        textual_section = runtime_section.get("textual", {})
        if not isinstance(textual_section, dict):
            textual_section = {}
        textual_section["theme_name"] = str(theme_name)
        textual_section["workspace_mode"] = str(workspace_mode)
        runtime_section["textual"] = textual_section

        if default_llm_profile:
            llm_section["default_profile"] = str(default_llm_profile)
        else:
            llm_section.pop("default_profile", None)

        self._runtime_config = runtime_section
        self._llm_config = llm_section
        config_path = self._write_workspace_config()
        self._reload_llm_runtime()
        return config_path

    @property
    def active_agent(self):
        return self.active_agent_profile

    @active_agent.setter
    def active_agent(self, value):
        self.active_agent_profile = value

    def set_agent(self, agent_name: Optional[str]) -> None:
        """Backward-compatible alias for selecting the current flow."""
        normalized_agent_name = self._normalize_agent_name(agent_name)
        if not normalized_agent_name:
            self.current_agent = None
            self.active_agent_profile = None
            self.active_mode = None
            return
        if normalized_agent_name not in self._plugins.agents:
            raise KeyError(f"Unknown agent '{agent_name}'.")
        self.active_mode = None
        self.current_agent = normalized_agent_name
        # T012: auto-activate the agent's default profile.
        self._activate_default_profile_for(normalized_agent_name)

    def set_flow(self, flow_name: Optional[str]) -> None:
        self.set_agent(flow_name)

    def set_active_agent_profile(self, name: Optional[str]) -> None:
        """Activate a named agent profile, or clear the active profile if name is None."""
        if name is None:
            self.active_agent_profile = None
            self.active_mode = None
            return
        profile = self._base_agent_profile(name)
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
        self.active_mode = None
        self.current_agent = self._normalize_agent_name(profile.agent)
        self.active_agent_profile = self._apply_textual_profile_overrides(profile)

    def set_active_agent(self, name: Optional[str]) -> None:
        self.set_active_agent_profile(name)

    def list_modes(self) -> List[str]:
        return [mode.name for mode in self._mode_manager.list()]

    def get_mode(self, name: Optional[str] = None) -> Any:
        if name is None:
            return self.active_mode
        return self._mode_manager.get(name)

    def set_mode(self, name: Optional[str]) -> None:
        if name is None:
            self.active_mode = None
            if self.current_agent:
                self._activate_default_profile_for(self.current_agent)
            else:
                self.active_agent_profile = None
            return

        mode = self._mode_manager.get(name)
        if mode is None:
            raise ValueError(f"Unknown mode '{name}'. Available: {self.list_modes()}")

        profile = self._resolve_mode_profile(mode)
        self.active_mode = mode
        self.current_agent = self._normalize_agent_name(profile.agent)
        self.active_agent_profile = self._apply_textual_profile_overrides(profile)

    def _normalize_agent_name(self, agent_name: Any) -> Optional[str]:
        cleaned = str(agent_name or "").strip()
        if not cleaned:
            return None

        agents_registry = getattr(self._plugins, "agents", None)
        if agents_registry is None:
            return cleaned.replace("::", ".")

        qualify = getattr(agents_registry, "qualify", None)
        if callable(qualify):
            try:
                return str(qualify(cleaned))
            except Exception:  # noqa: BLE001
                pass

        if cleaned in agents_registry:
            return cleaned

        canonical = cleaned.replace("::", ".")
        if canonical in agents_registry:
            return canonical

        legacy = cleaned.replace(".", "::")
        if legacy in agents_registry:
            return legacy

        return canonical

    def list_skills(self) -> List[str]:
        return [skill.name for skill in self._skill_manager.list()]

    def get_skill(self, name: str) -> Any:
        return self._skill_manager.get(name)

    def get_active_skills(self) -> List[Any]:
        return [
            skill
            for skill_name in self.enabled_skills
            if (skill := self._skill_manager.get(skill_name)) is not None
        ]

    def enable_skill(self, name: str) -> None:
        skill = self._skill_manager.get(name)
        if skill is None:
            raise ValueError(f"Unknown skill '{name}'. Available: {self.list_skills()}")
        if name not in self.enabled_skills:
            self.enabled_skills.append(name)
            self._refresh_runtime_components()

    def disable_skill(self, name: str) -> None:
        if name not in self.enabled_skills:
            return
        self.enabled_skills = [skill_name for skill_name in self.enabled_skills if skill_name != name]
        self._refresh_runtime_components()

    def set_last_used_skills(self, skill_names: List[str]) -> Path:
        normalized = self._normalize_skill_names(skill_names, strict=True)
        last_used = self._textual_last_used_config(create=True)
        last_used["skills"] = normalized
        self.enabled_skills = list(normalized)
        self._refresh_runtime_components()
        return self._write_workspace_config()

    def reset_last_used_skills(self) -> Path:
        last_used = self._textual_last_used_config(create=True)
        last_used.pop("skills", None)
        self._cleanup_textual_last_used_config()
        self.enabled_skills = self._configured_enabled_skills()
        self._refresh_runtime_components()
        return self._write_workspace_config()

    def save_default_skills(self, skill_names: List[str]) -> Path:
        normalized = self._normalize_skill_names(skill_names, strict=True)
        textual = self._textual_config(create=True)
        textual["default_skills"] = normalized
        return self._write_workspace_config()

    def set_last_used_active_profile(self, profile_name: Optional[str]) -> Path:
        last_used = self._textual_last_used_config(create=True)
        cleaned = str(profile_name).strip() if profile_name else ""
        if cleaned:
            self.set_active_agent_profile(cleaned)
            last_used["active_profile"] = cleaned
            last_used.pop("active_mode", None)
        else:
            last_used.pop("active_profile", None)
        self._cleanup_textual_last_used_config()
        return self._write_workspace_config()

    def set_last_used_mode(self, mode_name: Optional[str]) -> Path:
        last_used = self._textual_last_used_config(create=True)
        cleaned = str(mode_name).strip() if mode_name else ""
        if cleaned:
            self.set_mode(cleaned)
            last_used["active_mode"] = cleaned
            last_used.pop("active_profile", None)
        else:
            self.set_mode(None)
            last_used.pop("active_mode", None)
        self._cleanup_textual_last_used_config()
        return self._write_workspace_config()

    def set_last_used_global_llm_profile(self, profile_name: Optional[str]) -> Path:
        last_used = self._textual_last_used_config(create=True)
        cleaned = str(profile_name).strip() if profile_name else ""
        if cleaned:
            self.set_global_llm_override(cleaned)
            last_used["global_llm_profile"] = cleaned
        else:
            self.set_global_llm_override(None)
            last_used.pop("global_llm_profile", None)
        self._cleanup_textual_last_used_config()
        return self._write_workspace_config()

    def set_last_used_session_confirmation_default(self, policy: Optional[str]) -> Path:
        last_used = self._textual_last_used_config(create=True)
        normalized = self._normalize_confirmation_policy(policy)
        self.set_session_confirmation_default(normalized)
        if normalized is None:
            last_used.pop("session_confirmation_default", None)
        else:
            last_used["session_confirmation_default"] = normalized
        self._cleanup_textual_last_used_config()
        return self._write_workspace_config()

    def set_last_used_auto_confirm_tools(self, enabled: bool) -> Path:
        last_used = self._textual_last_used_config(create=True)
        self.auto_confirm_tools = bool(enabled)
        if self.auto_confirm_tools == bool(self._runtime_config.get("auto_confirm_tools", False)):
            last_used.pop("auto_confirm_tools", None)
        else:
            last_used["auto_confirm_tools"] = self.auto_confirm_tools
        self._cleanup_textual_last_used_config()
        return self._write_workspace_config()

    def list_textual_selection_presets(self) -> List[str]:
        presets = self._textual_selection_presets_config(create=False)
        return sorted(str(name) for name in presets)

    def get_textual_selection_preset(self, name: str) -> Dict[str, Any] | None:
        presets = self._textual_selection_presets_config(create=False)
        raw = presets.get(name)
        if not isinstance(raw, dict):
            return None
        return self._normalize_textual_selection_snapshot(raw)

    def save_textual_selection_preset(self, name: str) -> Path:
        cleaned = str(name).strip()
        if not cleaned:
            raise ValueError("Selection preset name cannot be empty.")
        presets = self._textual_selection_presets_config(create=True)
        presets[cleaned] = self._capture_textual_selection_snapshot()
        return self._write_workspace_config()

    def apply_textual_selection_preset(self, name: str) -> Path:
        preset = self.get_textual_selection_preset(name)
        if preset is None:
            raise ValueError(f"Unknown selection preset '{name}'.")
        self._replace_last_used_selection_snapshot(preset)
        self.active_mode = None
        self.active_agent_profile = None
        self.global_llm_override = None
        self.clear_session_confirmation_overrides()
        self.auto_confirm_tools = bool(self._runtime_config.get("auto_confirm_tools", False))
        self._restore_textual_selection_state()
        return self._write_workspace_config()

    def delete_textual_selection_preset(self, name: str) -> Path:
        presets = self._textual_selection_presets_config(create=True)
        cleaned = str(name).strip()
        if cleaned not in presets:
            raise ValueError(f"Unknown selection preset '{cleaned}'.")
        presets.pop(cleaned, None)
        if not presets:
            textual = self._textual_config(create=True)
            textual.pop("selection_presets", None)
        return self._write_workspace_config()

    def list_agent_profiles(self, agent_name: Optional[str] = None) -> List[str]:
        """Return known agent profile names, optionally filtered by target agent."""
        profiles = self._agent_profile_manager.list()
        if agent_name:
            profiles = [profile for profile in profiles if profile.agent == agent_name]
        return sorted({p.name for p in profiles})

    def list_available_agents(self, flow_name: Optional[str] = None) -> List[str]:
        return self.list_agent_profiles(flow_name)

    def get_agent_profile(self, name: Optional[str] = None, *, effective: bool = True) -> Any:
        """Return a named agent profile, or the active one when *name* is None."""
        if name is None:
            if effective:
                return self.active_agent_profile
            if self.active_agent_profile is None:
                return None
            return self._base_agent_profile(self.active_agent_profile.name) or self.active_agent_profile
        profile = self._base_agent_profile(name)
        if profile is None and self.active_agent_profile is not None and self.active_agent_profile.name == name:
            profile = self.active_agent_profile
        if not effective or profile is None:
            return profile
        return self._apply_textual_profile_overrides(profile)

    def get_agent(self, name: Optional[str] = None) -> Any:
        return self.get_agent_profile(name)

    def clone_agent_profile(self, src_name: str, new_name: str) -> Any:
        """Clone an agent profile and return the new workspace-backed profile."""
        return self._agent_profile_manager.clone(src_name, new_name)

    def clone_agent(self, src_name: str, new_name: str) -> Any:
        return self.clone_agent_profile(src_name, new_name)

    def clone_llm_profile(self, src_name: str, new_name: str) -> Any:
        profile = self.get_llm_profile(src_name)
        if profile is None:
            raise ValueError(f"Unknown LLM profile '{src_name}'.")
        cloned = self._workspace_llm_profile_manager.clone(
            src_name,
            new_name,
            profile.get("config", {}),
        )
        self._reload_llm_runtime()
        return {
            "name": new_name,
            "source": "workspace",
            "source_path": cloned.get("source_path"),
            "config": copy.deepcopy(cloned.get("config", {})),
        }

    def delete_agent_profile(self, name: str) -> Path:
        target_path = self._agent_profile_manager.delete(name)
        if self.active_agent_profile is not None and self.active_agent_profile.name == name:
            self.active_agent_profile = None
        selection = self._textual_last_used_config(create=True)
        if selection.get("active_profile") == name:
            selection.pop("active_profile", None)
        self._cleanup_textual_profile_state(name)
        self._cleanup_invalid_textual_selection_presets(removed_profile=name)
        if self.current_agent:
            self._activate_default_profile_for(self.current_agent)
        return self._write_workspace_config()

    def delete_llm_profile(self, name: str) -> Path:
        profile = self.get_llm_profile(name)
        if profile is None or profile.get("source") != "workspace":
            raise ValueError(
                f"LLM profile '{name}' is not workspace-backed. Only workspace LLM profiles can be deleted."
            )
        target_path = self._workspace_llm_profile_manager.delete(name)
        if self.global_llm_override == name:
            self.global_llm_override = None
        selection = self._textual_last_used_config(create=True)
        if selection.get("global_llm_profile") == name:
            selection.pop("global_llm_profile", None)
        self._cleanup_invalid_textual_selection_presets(removed_llm=name)
        self._reload_llm_runtime()
        return self._write_workspace_config()

    def get_mode_text(self, name: str) -> str:
        return self._mode_manager.get_mode_text(name)

    def clone_mode(self, src_name: str, new_name: str) -> Path:
        target_path = self._mode_manager.clone(src_name, new_name)
        self._mode_manager.load()
        return target_path

    def update_mode(self, name: str, *, markdown_text: str) -> Path:
        target_path = self._mode_manager.save_text(name, markdown_text)
        self._mode_manager.load()
        if self.active_mode is not None and self.active_mode.name == name:
            self.set_mode(name)
        return target_path

    def delete_mode(self, name: str) -> Path:
        target_path = self._mode_manager.delete(name)
        if self.active_mode is not None and self.active_mode.name == name:
            self.set_mode(None)
        selection = self._textual_last_used_config(create=True)
        if selection.get("active_mode") == name:
            selection.pop("active_mode", None)
        self._cleanup_invalid_textual_selection_presets(removed_mode=name)
        return self._write_workspace_config()

    def update_llm_profile(self, name: str, *, profile_config: Dict[str, Any]) -> Any:
        profile = self.get_llm_profile(name)
        if profile is None:
            raise ValueError(f"Unknown LLM profile '{name}'.")
        if profile.get("source") != "workspace":
            raise ValueError(
                f"LLM profile '{name}' is not workspace-backed. Clone it before editing."
            )
        self._workspace_llm_profile_manager.save(name, profile_config)
        self._reload_llm_runtime()
        return self.get_llm_profile(name)

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
        profile = self._base_agent_profile(name)
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
            self.active_agent_profile = self._apply_textual_profile_overrides(refreshed)
        return refreshed

    def set_last_used_profile_tools(self, profile_name: str, tools: Optional[List[str]]) -> Path:
        profile = self._base_agent_profile(profile_name)
        if profile is None and (self.active_agent_profile is None or self.active_agent_profile.name != profile_name):
            raise ValueError(f"Unknown agent profile '{profile_name}'.")
        normalized_tools = self._normalize_tool_list(tools)
        base_tools = self._normalize_tool_list(profile.tools) if profile is not None else None
        if normalized_tools == base_tools:
            return self.reset_last_used_profile_tools(profile_name)
        profile_state = self._textual_profile_state(profile_name, create=True)
        profile_state["tools"] = normalized_tools
        self._refresh_active_profile(profile_name)
        return self._write_workspace_config()

    def reset_last_used_profile_tools(self, profile_name: str) -> Path:
        profile_state = self._textual_profile_state(profile_name, create=True)
        profile_state.pop("tools", None)
        self._cleanup_textual_profile_state(profile_name)
        self._refresh_active_profile(profile_name)
        return self._write_workspace_config()

    def set_last_used_profile_tool_policies(self, profile_name: str, overrides: Dict[str, Optional[str]]) -> Path:
        profile = self._base_agent_profile(profile_name)
        if profile is None and (self.active_agent_profile is None or self.active_agent_profile.name != profile_name):
            raise ValueError(f"Unknown agent profile '{profile_name}'.")
        normalized_overrides = self._normalized_confirmation_overrides(overrides)
        base_overrides = (
            self._normalized_confirmation_overrides(profile.tool_confirmation.get("overrides", {}))
            if profile is not None and isinstance(profile.tool_confirmation, dict)
            else {}
        )
        if normalized_overrides == base_overrides:
            return self.reset_last_used_profile_tool_policies(profile_name)
        profile_state = self._textual_profile_state(profile_name, create=True)
        profile_state["tool_confirmation_overrides"] = normalized_overrides
        self._refresh_active_profile(profile_name)
        return self._write_workspace_config()

    def reset_last_used_profile_tool_policies(self, profile_name: str) -> Path:
        profile_state = self._textual_profile_state(profile_name, create=True)
        profile_state.pop("tool_confirmation_overrides", None)
        self._cleanup_textual_profile_state(profile_name)
        self._refresh_active_profile(profile_name)
        return self._write_workspace_config()

    def update_agent(
        self,
        name: str,
        *,
        llm_profile: Optional[str],
        tools: Optional[List[str]],
        extra_prompts: List[str],
        tool_confirmation_default: Optional[str],
        tool_confirmation_overrides: Optional[Dict[str, Optional[str]]] = None,
    ) -> Any:
        return self.update_agent_profile(
            name,
            llm_profile=llm_profile,
            tools=tools,
            extra_prompts=extra_prompts,
            tool_confirmation_default=tool_confirmation_default,
            tool_confirmation_overrides=tool_confirmation_overrides,
        )

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
            for tool_name in self._active_skill_existing_tool_refs():
                if tool_name not in tool_names:
                    tool_names.append(tool_name)
            for tool_name in self._active_skill_provided_tools().keys():
                if tool_name not in tool_names:
                    tool_names.append(tool_name)
        sorted_tool_names = sorted(tool_names)
        if not apply_active_profile:
            self._agent_tools_cache[agent_name] = list(sorted_tool_names)
        return sorted_tool_names

    def list_tools_for_flow(
        self,
        flow_name: str,
        *,
        apply_active_agent: bool = False,
    ) -> List[str]:
        return self.list_tools_for_agent(flow_name, apply_active_profile=apply_active_agent)

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

    def describe_flow(self, flow_name: Optional[str] = None) -> Dict[str, Any]:
        return self.describe_agent(flow_name)

    def get_agent_prompt_sources(self, agent_name: Optional[str] = None) -> List[str]:
        """Return prompt source paths for the target agent."""
        target = agent_name or self.current_agent
        if not target:
            return []
        definition = self._plugins.agents.get(target)
        if definition is None:
            raise KeyError(f"Unknown agent '{target}'.")
        return list(definition.prompt_sources)

    def get_flow_prompt_sources(self, flow_name: Optional[str] = None) -> List[str]:
        return self.get_agent_prompt_sources(flow_name)

    def _activate_default_profile_for(self, agent_name: str) -> None:
        """Set active_agent_profile to the agent's default profile."""
        profile = self._get_default_profile_for(agent_name)
        self.active_agent_profile = self._apply_textual_profile_overrides(profile)

    def _get_default_profile_for(self, agent_name: str) -> Any:
        defn = self._plugins.agents.get(agent_name)
        if defn is None:
            return None
        explicit = getattr(defn, "default_agent_profile", None)
        if explicit is not None:
            default_name = explicit.name
        else:
            default_name = agent_name  # synthesised profile is named after the agent
        profile = self._base_agent_profile(default_name)
        if profile is None:
            # Fall back to any profile whose agent field matches.
            for p in self._agent_profile_manager.list():
                if p.agent == agent_name:
                    profile = p
                    break
        return profile

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

    def set_flow_llm_override(self, flow_name: str, profile_name: Optional[str]) -> None:
        self.set_agent_llm_override(flow_name, profile_name)

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
        for tool_name in self._active_skill_existing_tool_refs():
            if tool_name not in tool_names:
                tool_names.append(tool_name)
        for tool_name in self._active_skill_provided_tools().keys():
            if tool_name not in tool_names:
                tool_names.append(tool_name)
        return self._tool_runtime.describe_tools(tool_names)

    def describe_tools_for_flow(self, flow_name: str) -> List[Dict[str, Any]]:
        return self.describe_tools_for_agent(flow_name)

    def describe_tool(self, tool_name: str) -> Dict[str, Any]:
        return self._tool_runtime.describe_tool(tool_name)

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
            interaction_handler=handle.request_interaction if bridge_user_input else None,
            user_input_handler=handle.request_user_input if bridge_user_input else None,
            run_handle=handle,
        )

        def runner() -> None:
            try:
                handle.emit(
                    "run_started",
                    request=user_input,
                    agent=shared_store.get("active_agent") or "auto",
                )
                result = self._execute_request(shared_store=shared_store, cli_context=cli_context)
                self._finalize_active_session(shared_store=shared_store, final_output=result)
                handle.complete(result=result, summary=self._build_run_summary(shared_store, cli_context))
            except RunCancelledError as exc:
                summary = self._build_run_summary(shared_store, cli_context)
                self.last_run_summary = dict(summary)
                self._finalize_active_session(shared_store=shared_store, cancellation_reason=str(exc))
                handle.cancelled(reason=str(exc), summary=summary)
            except Exception as exc:
                logger.error("Request processing failed: %s", exc, exc_info=True)
                self.last_run_summary = dict(self._build_run_summary(shared_store, cli_context))
                self._finalize_active_session(shared_store=shared_store, error=str(exc))
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
        interaction_handler: Any = None,
        user_input_handler: Any = None,
        run_handle: RunHandle | None = None,
    ) -> Dict[str, Any]:
        initial_agent = self.current_agent or self._runtime_config.get("default_agent")
        if not initial_agent:
            agents = self.list_agents()
            if agents:
                initial_agent = agents[0]

        active_mode = getattr(self, "active_mode", None)
        active_skills = self.get_active_skills() if hasattr(self, "get_active_skills") else []
        active_skill_existing_tool_refs = (
            self._active_skill_existing_tool_refs()
            if hasattr(self, "_active_skill_existing_tool_refs")
            else []
        )
        active_skill_tool_names = (
            list(self._active_skill_provided_tools().keys())
            if hasattr(self, "_active_skill_provided_tools")
            else []
        )

        shared_store: Dict[str, Any] = {
            "run_id": uuid4().hex,
            "initial_request": user_input,
            "cli_context": self._copy_cli_context(cli_context),
            "formatted_cli_context": self._format_cli_context(cli_context),
            "active_flow": initial_agent,
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
            "active_mode": active_mode.name if active_mode is not None else None,
            "active_skills": active_skills,
            "active_skill_existing_tool_refs": active_skill_existing_tool_refs,
            "active_skill_tool_names": active_skill_tool_names,
            "active_session_id": getattr(self, "active_session_id", None),
            "active_session_title": getattr(self, "active_session_title", None),
            "active_session_loaded_from_history": bool(getattr(self, "active_session_loaded_from_history", False)),
            "replace_session_confirmation_overrides": self.replace_session_confirmation_overrides,
            "persist_tool_confirmation": self.set_persistent_tool_confirmation,
        }
        if callable(event_handler):
            shared_store["runtime_event_handler"] = event_handler
        if callable(interaction_handler):
            shared_store["interaction_handler"] = interaction_handler
        if callable(user_input_handler):
            shared_store["user_input_handler"] = user_input_handler
        if run_handle is not None:
            shared_store["run_cancel_requested"] = lambda: run_handle.is_cancel_requested
            shared_store["run_cancel_reason"] = lambda: run_handle.cancel_reason
        return shared_store

    def _execute_request(self, *, shared_store: Dict[str, Any], cli_context: Dict[str, Any]) -> str:
        self._agent_runtime.run(shared_store)

        if shared_store.get("active_agent"):
            self.current_agent = shared_store["active_agent"]

        self.last_run_summary = self._build_run_summary(shared_store, cli_context)

        return str(shared_store.get("final_output") or shared_store.get("final_answer") or "No output generated.")

    def _build_run_summary(self, shared_store: Dict[str, Any], cli_context: Dict[str, Any]) -> Dict[str, Any]:
        active_mode = getattr(self, "active_mode", None)
        return {
            "agent_path": self._build_agent_path(shared_store),
            "current_agent": shared_store.get("active_agent") or self.current_agent,
            "active_mode": shared_store.get("active_mode") or (active_mode.name if active_mode else None),
            "active_skills": [skill.name for skill in shared_store.get("active_skills", []) or []],
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

    def status(self) -> Dict[str, Any]:
        selected_agent = self.active_agent_profile.name if self.active_agent_profile else None
        selected_llm_profile = self._selected_llm_profile()
        active_mode = getattr(self, "active_mode", None)
        runtime_flow = (
            self._runtime_config.get("agent_runtime_flow")
            or self._runtime_config.get("agent_runtime_workflow")
        )
        return {
            "flow": self.current_agent,
            "agent": selected_agent,
            "selected_flow": self.current_agent,
            "selected_agent": selected_agent,
            "selected_llm_profile": selected_llm_profile,
            "mode": active_mode.name if active_mode else None,
            "skills": list(self.enabled_skills),
            "runtime_flow": runtime_flow,
            # T013: expose active agent profile name.
            "active_agent_profile": selected_agent,
            "active_agent": selected_agent,
            "global_llm_override": self.global_llm_override,
            "agent_llm_overrides": dict(self.agent_llm_overrides),
            "handoff_llm_overrides": dict(self.handoff_llm_overrides),
            "config_llm_overrides": dict(self.config_llm_overrides),
            "default_llm_profile": self.default_llm_profile,
            "tool_confirmation": self._tool_confirmation_config,
            "session_tool_confirmation_overrides": self._copy_session_confirmation_overrides(),
            "active_session_id": getattr(self, "active_session_id", None),
            "active_session_title": getattr(self, "active_session_title", None),
            "active_session_loaded_from_history": bool(getattr(self, "active_session_loaded_from_history", False)),
            "active_session": {
                "session_id": getattr(self, "active_session_id", None),
                "title": getattr(self, "active_session_title", None),
                "loaded_from_history": bool(getattr(self, "active_session_loaded_from_history", False)),
            },
            "available_flows": self.list_flows(),
            "available_agents": self.list_available_agents(),
            "available_modes": self.list_modes(),
            "available_skills": self.list_skills(),
            "available_llm_profiles": self.list_llm_profiles(),
            "last_run_summary": dict(self.last_run_summary),
        }

    def get_active_session_info(self) -> Dict[str, Any]:
        self._ensure_active_session()
        updated_at = None
        session_manager = getattr(self, "_session_manager", None)
        session_id = getattr(self, "active_session_id", None)
        if session_manager is not None and session_id:
            try:
                updated_at = session_manager.load_session(session_id).updated_at
            except Exception:
                updated_at = None
        return {
            "session_id": session_id,
            "title": getattr(self, "active_session_title", None),
            "updated_at": updated_at,
            "loaded_from_history": bool(getattr(self, "active_session_loaded_from_history", False)),
        }

    def list_saved_sessions(self) -> List[Dict[str, Any]]:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            return []
        self._ensure_active_session()
        active_session_id = getattr(self, "active_session_id", None)
        items: list[Dict[str, Any]] = []
        for summary in session_manager.list_session_summaries():
            item = summary.as_dict()
            item["is_active"] = summary.session_id == active_session_id
            item["is_resumable"] = summary.session_id != active_session_id
            items.append(item)
        return items

    def start_new_session(self, title: str | None = None) -> Dict[str, Any]:
        self._update_active_session_snapshot()
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            raise RuntimeError("Session persistence is not available.")
        self.clear_session_confirmation_overrides()
        record = session_manager.create_session(title=title, state=self._session_state_payload())
        self.active_session_id = record.session_id
        self.active_session_title = record.title
        self.active_session_loaded_from_history = False
        return self.get_active_session_info()

    def resume_session(self, session_id: str) -> Dict[str, Any]:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            raise RuntimeError("Session persistence is not available.")

        record = session_manager.load_session(session_id)
        self._restore_saved_session(record)
        self.active_session_id = record.session_id
        self.active_session_title = record.title
        self.active_session_loaded_from_history = True
        self._update_active_session_snapshot()
        return self.get_active_session_info()

    def delete_session(self, session_id: str) -> Dict[str, Any]:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            raise RuntimeError("Session persistence is not available.")
        target_id = str(session_id or "").strip()
        if not target_id:
            raise ValueError("Session id is required.")
        if target_id == getattr(self, "active_session_id", None):
            raise ValueError("Cannot delete the active session.")
        if not session_manager.session_exists(target_id):
            raise ValueError(f"Unknown session '{target_id}'.")
        if not session_manager.delete_session(target_id):
            raise ValueError(f"Unknown session '{target_id}'.")
        return {"session_id": target_id, "deleted": True}

    def clear_saved_sessions(self) -> int:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            raise RuntimeError("Session persistence is not available.")
        self._ensure_active_session()
        active_session_id = getattr(self, "active_session_id", None)
        excluded = [active_session_id] if active_session_id else []
        return session_manager.clear_sessions(exclude_ids=excluded)

    def _selected_llm_profile(self) -> Optional[str]:
        if self.active_agent_profile is not None and self.active_agent_profile.llm_profile:
            return self.active_agent_profile.llm_profile
        return self.global_llm_override or self.default_llm_profile

    def set_session_confirmation_default(self, policy: Optional[str]) -> None:
        self.session_confirmation_overrides["default_policy"] = self._normalize_confirmation_policy(policy)

    def set_session_tool_confirmation(self, tool_name: str, policy: Optional[str]) -> None:
        self._set_policy_entry(self.session_confirmation_overrides["tool_policies"], tool_name, policy)

    def replace_session_confirmation_overrides(self, overrides: Dict[str, Any]) -> None:
        normalized = {
            "default_policy": self._normalize_confirmation_policy(overrides.get("default_policy"))
            if overrides.get("default_policy") is not None
            else None,
            "tool_policies": {},
            "agent_policies": {},
        }

        raw_tool_policies = overrides.get("tool_policies", {})
        if isinstance(raw_tool_policies, dict):
            for tool_name, policy in raw_tool_policies.items():
                try:
                    normalized_policy = self._normalize_confirmation_policy(policy)
                except ValueError:
                    continue
                if normalized_policy is not None:
                    normalized["tool_policies"][str(tool_name)] = normalized_policy

        raw_agent_policies = overrides.get("agent_policies", {})
        if isinstance(raw_agent_policies, dict):
            for agent_name, raw_policy in raw_agent_policies.items():
                if not isinstance(raw_policy, dict):
                    continue
                entry = {"default_policy": None, "tool_policies": {}}
                if raw_policy.get("default_policy") is not None:
                    try:
                        entry["default_policy"] = self._normalize_confirmation_policy(raw_policy.get("default_policy"))
                    except ValueError:
                        entry["default_policy"] = None
                raw_entry_tools = raw_policy.get("tool_policies", {})
                if isinstance(raw_entry_tools, dict):
                    for tool_name, policy in raw_entry_tools.items():
                        try:
                            normalized_policy = self._normalize_confirmation_policy(policy)
                        except ValueError:
                            continue
                        if normalized_policy is not None:
                            entry["tool_policies"][str(tool_name)] = normalized_policy
                if entry["default_policy"] is not None or entry["tool_policies"]:
                    normalized["agent_policies"][str(agent_name)] = entry

        self.session_confirmation_overrides = normalized
        self._update_active_session_snapshot()

    def set_persistent_tool_confirmation(self, tool_name: str, policy: Optional[str]) -> Path:
        runtime_section = self._config.setdefault("runtime", {})
        if not isinstance(runtime_section, dict):
            runtime_section = {}
            self._config["runtime"] = runtime_section
        confirmation_section = runtime_section.setdefault("tool_confirmation", {})
        if not isinstance(confirmation_section, dict):
            confirmation_section = {}
            runtime_section["tool_confirmation"] = confirmation_section
        tool_policies = confirmation_section.setdefault("tool_policies", {})
        if not isinstance(tool_policies, dict):
            tool_policies = {}
            confirmation_section["tool_policies"] = tool_policies
        self._set_policy_entry(tool_policies, tool_name, policy)
        self._runtime_config = runtime_section
        self._tool_confirmation_config = self._build_tool_confirmation_config()
        self._refresh_runtime_components()
        return self._write_workspace_config()

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

    def _restore_saved_session(self, record: Any) -> None:
        active_mode_name = str(getattr(record, "active_mode", "") or "").strip()
        active_profile_name = str(getattr(record, "active_profile", "") or "").strip()
        active_agent_name = str(getattr(record, "active_agent", "") or "").strip()
        llm_profile_name = str(getattr(record, "global_llm_profile", "") or "").strip()

        self.active_mode = None
        self.active_agent_profile = None
        self.current_agent = None

        if active_mode_name:
            try:
                self.set_mode(active_mode_name)
            except Exception:
                logger.warning("Saved session mode '%s' is unavailable; falling back.", active_mode_name)

        if self.active_mode is None and active_profile_name:
            try:
                self.set_active_agent_profile(active_profile_name)
            except Exception:
                logger.warning("Saved session profile '%s' is unavailable; falling back.", active_profile_name)

        if self.active_mode is None and self.active_agent_profile is None and active_agent_name:
            try:
                self.set_agent(active_agent_name)
            except Exception:
                logger.warning("Saved session agent '%s' is unavailable.", active_agent_name)

        normalized_skills = self._normalize_skill_names(getattr(record, "enabled_skills", []) or [], strict=False)
        self.enabled_skills = list(normalized_skills)

        try:
            self.set_global_llm_override(llm_profile_name or None)
        except Exception:
            logger.warning("Saved session LLM '%s' is unavailable; clearing override.", llm_profile_name)
            self.set_global_llm_override(None)

        self.replace_session_confirmation_overrides(
            dict(getattr(record, "session_confirmation_overrides", {}) or {})
        )
        self._refresh_runtime_components()

    def _copy_cli_context(self, cli_context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "files": sorted(list(cli_context.get("files", set()))),
            "folders": sorted(list(cli_context.get("folders", set()))),
            "urls": sorted(list(cli_context.get("urls", set()))),
            "snippets": dict(cli_context.get("snippets", {})),
        }

    def _build_tool_runtime(self) -> ToolRuntime:
        merged_tools = dict(self._plugins.tools.items())
        merged_tools.update(self._active_skill_provided_tools())
        return ToolRuntime(
            tools=merged_tools,
            require_confirmation=bool(self._runtime_config.get("require_tool_confirmation", True)),
            auto_approved_tools=list(self._runtime_config.get("auto_approved_tools", [])),
            confirmation_config=self._tool_confirmation_config,
        )

    def _active_skill_provided_tools(self) -> Dict[str, Any]:
        tools: Dict[str, Any] = {}
        for skill in self.get_active_skills():
            tools.update(skill.provided_tools)
        return tools

    def _active_skill_existing_tool_refs(self) -> List[str]:
        resolved: list[str] = []
        for skill in self.get_active_skills():
            for tool_ref in skill.tool_refs:
                qualified = self._qualify_tool_reference(
                    tool_ref,
                    context_agent=self.current_agent,
                )
                if qualified and qualified not in resolved:
                    resolved.append(qualified)
        return resolved

    def _resolve_mode_profile(self, mode: ModeDefinition) -> AgentProfile:
        base_profile: AgentProfile | None = None
        if mode.agent:
            base_profile = self._agent_profile_manager.get(mode.agent)
            if base_profile is None:
                raise ValueError(f"Mode '{mode.name}' references unknown agent profile '{mode.agent}'.")
        elif mode.flow:
            base_profile = self._agent_profile_manager.get(mode.flow) or self._get_default_profile_for(mode.flow)
        elif self.active_agent_profile is not None:
            base_profile = self.active_agent_profile
        elif self.current_agent:
            base_profile = self._get_default_profile_for(self.current_agent)

        target_flow = mode.flow or (base_profile.agent if base_profile is not None else None) or self.current_agent
        if not target_flow:
            raise ValueError(f"Mode '{mode.name}' could not resolve a target flow.")
        if target_flow not in self._plugins.agents:
            raise ValueError(f"Mode '{mode.name}' targets unknown flow '{target_flow}'.")

        if mode.llm_profile:
            self._llm_router.resolve_profile_config(mode.llm_profile)

        context_agent = target_flow
        if mode.tools_specified:
            if mode.tools is None:
                tools = None
            else:
                tools = [
                    qualified
                    for qualified in (
                        self._qualify_tool_reference(tool_ref, context_agent=context_agent)
                        for tool_ref in mode.tools
                    )
                    if qualified
                ]
        else:
            tools = list(base_profile.tools) if base_profile is not None and base_profile.tools is not None else None

        base_confirmation = dict(base_profile.tool_confirmation or {}) if base_profile is not None else {}
        mode_confirmation = dict(mode.tool_confirmation or {})
        merged_confirmation: Dict[str, Any] = {}
        merged_default = mode_confirmation.get("default", base_confirmation.get("default"))
        if merged_default:
            merged_confirmation["default"] = self._normalize_confirmation_policy(str(merged_default))
        merged_overrides = dict(base_confirmation.get("overrides", {}))
        merged_overrides.update(mode_confirmation.get("overrides", {}))
        normalized_overrides = {
            str(tool_name): normalized
            for tool_name, policy in merged_overrides.items()
            if (normalized := self._normalize_confirmation_policy(str(policy))) is not None
        }
        if normalized_overrides:
            merged_confirmation["overrides"] = normalized_overrides

        inherited_extra_prompts = list(base_profile.extra_prompts) if base_profile is not None else []
        inline_parts = []
        if base_profile is not None and base_profile.inline_prompt:
            inline_parts.append(base_profile.inline_prompt)
        if mode.inline_prompt:
            inline_parts.append(mode.inline_prompt)

        return AgentProfile(
            name=mode.name,
            flow=target_flow,
            description=mode.description or (base_profile.description if base_profile is not None else ""),
            llm_profile=mode.llm_profile or (base_profile.llm_profile if base_profile is not None else None),
            inline_prompt="\n\n".join(part for part in inline_parts if part),
            extra_prompts=inherited_extra_prompts + list(mode.extra_prompts),
            tools=tools,
            tool_confirmation=merged_confirmation,
            source="mode",
            source_path=mode.source_path,
        )

    def _qualify_tool_reference(
        self,
        tool_ref: str,
        *,
        context_agent: str | None,
    ) -> str | None:
        candidate = str(tool_ref or "").strip()
        if not candidate:
            return None
        if candidate.startswith("skill."):
            return candidate
        context_plugin = None
        if context_agent:
            agent_definition = self._plugins.agents.get(context_agent)
            if agent_definition is not None:
                context_plugin = (agent_definition.metadata or {}).get("plugin")
        try:
            return self._plugins.tools.qualify(candidate, context_plugin=context_plugin)
        except RegistryError as exc:
            raise ValueError(str(exc)) from exc

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

    def _session_state_payload(self, shared_store: Dict[str, Any] | None = None) -> Dict[str, Any]:
        source = shared_store or {}
        active_profile = source.get("active_agent_profile", self.active_agent_profile)
        active_skills = source.get("active_skills")
        if active_skills is None:
            active_skills = self.get_active_skills()
        skill_names = [
            skill.name if hasattr(skill, "name") else str(skill)
            for skill in active_skills or []
        ]
        active_mode = source.get("active_mode")
        current_active_mode = getattr(self, "active_mode", None)
        if not active_mode and current_active_mode is not None:
            active_mode = current_active_mode.name
        return {
            "active_agent": source.get("active_agent") or self.current_agent,
            "active_profile": getattr(active_profile, "name", None),
            "active_mode": active_mode,
            "enabled_skills": skill_names,
            "global_llm_profile": source.get("cli_llm_override") or self.global_llm_override,
            "session_confirmation_overrides": dict(
                source.get("session_tool_confirmation")
                if isinstance(source.get("session_tool_confirmation"), dict)
                else self._copy_session_confirmation_overrides()
            ),
        }

    def _ensure_active_session(self) -> None:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            return
        session_id = getattr(self, "active_session_id", None)
        if session_id:
            try:
                record = session_manager.load_session(session_id)
            except Exception:
                logger.warning("Active session '%s' could not be loaded; creating a fresh session.", session_id)
            else:
                self.active_session_title = record.title
                return
        record = session_manager.create_session(state=self._session_state_payload())
        self.active_session_id = record.session_id
        self.active_session_title = record.title
        self.active_session_loaded_from_history = False

    def _update_active_session_snapshot(self, shared_store: Dict[str, Any] | None = None) -> None:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            return
        self._ensure_active_session()
        session_id = getattr(self, "active_session_id", None)
        if not session_id:
            return
        record = session_manager.update_session(session_id, **self._session_state_payload(shared_store))
        self.active_session_title = record.title

    def _finalize_active_session(
        self,
        *,
        shared_store: Dict[str, Any],
        final_output: str | None = None,
        error: str | None = None,
        cancellation_reason: str | None = None,
    ) -> None:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            return
        self._update_active_session_snapshot(shared_store)
        session_id = getattr(self, "active_session_id", None)
        if not session_id:
            return

        run_id = str(shared_store.get("run_id") or "") or None
        initial_request = str(shared_store.get("initial_request") or "").strip()
        if initial_request:
            session_manager.append_transcript_entry(
                session_id,
                role="user",
                content=initial_request,
                run_id=run_id,
                metadata={"agent": shared_store.get("active_agent")},
            )

        transcript_payload = None
        transcript_role = "assistant"
        if final_output:
            transcript_payload = str(final_output)
        elif cancellation_reason:
            transcript_role = "system"
            transcript_payload = f"Run cancelled: {cancellation_reason}"
        elif error:
            transcript_role = "system"
            transcript_payload = f"Run failed: {error}"

        if transcript_payload:
            session_manager.append_transcript_entry(
                session_id,
                role=transcript_role,
                content=transcript_payload,
                run_id=run_id,
                metadata={"summary": dict(self.last_run_summary)},
            )

        event_handler = shared_store.get("runtime_event_handler")
        if callable(event_handler):
            saved_record = session_manager.load_session(session_id)
            event_handler(
                "session_saved",
                session_id=session_id,
                title=saved_record.title,
                transcript_entries=len(saved_record.transcript),
            )

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

    def _merged_llm_profiles(self) -> Dict[str, Dict[str, Any]]:
        merged = dict(self._plugins.llm_profiles)
        merged.update(self._workspace_llm_profile_manager.list_profiles())
        return merged

    def _reload_llm_runtime(self) -> None:
        self._workspace_llm_profile_manager.load()
        self._llm_router = LlmRouter(config=self._config, plugin_llm_profiles=self._merged_llm_profiles())
        self.default_llm_profile = (
            self._llm_config.get("default_profile")
            or self._llm_router.default_profile_name
        )
        self.config_llm_overrides = self._build_llm_overrides_config()
        self._refresh_runtime_components()

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

    def _refresh_runtime_components(self) -> None:
        self._tool_runtime = self._build_tool_runtime()
        self._agent_runtime = AgentRuntime(
            plugin_manager=self._plugins,
            llm_router=self._llm_router,
            tool_runtime=self._tool_runtime,
            runtime_config=self._runtime_config,
        )

    def _restore_textual_selection_state(self) -> None:
        snapshot = self._current_last_used_selection_snapshot()
        selected_mode = str(snapshot.get("active_mode") or "").strip()
        selected_profile = str(snapshot.get("active_profile") or "").strip()
        selected_llm = str(snapshot.get("global_llm_profile") or "").strip()
        session_default = snapshot.get("session_confirmation_default")

        if "auto_confirm_tools" in snapshot:
            self.auto_confirm_tools = bool(snapshot.get("auto_confirm_tools"))

        if session_default is not None:
            self.set_session_confirmation_default(session_default)

        if selected_mode and self._mode_manager.get(selected_mode) is not None:
            self.set_mode(selected_mode)
        elif selected_profile and self._base_agent_profile(selected_profile) is not None:
            self.set_active_agent_profile(selected_profile)

        if selected_llm:
            try:
                self.set_global_llm_override(selected_llm)
            except Exception:
                logger.warning("Ignoring missing last-used LLM profile '%s'.", selected_llm)

    def _write_workspace_config(self) -> Path:
        config_path = self._workspace_root / WORKSPACE_SETTINGS_FILENAME
        config_path.write_text(
            yaml.safe_dump(self._config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return config_path

    def _textual_config(self, *, create: bool) -> Dict[str, Any]:
        if not hasattr(self, "_config") or not isinstance(self._config, dict):
            self._config = {}
        runtime_section = self._config.setdefault("runtime", {}) if create else self._config.get("runtime", {})
        if not isinstance(runtime_section, dict):
            runtime_section = {}
            if create:
                self._config["runtime"] = runtime_section
        textual = runtime_section.get("textual", {})
        if not isinstance(textual, dict):
            textual = {}
            if create:
                runtime_section["textual"] = textual
        elif create:
            runtime_section["textual"] = textual
        return textual

    def _textual_last_used_config(self, *, create: bool) -> Dict[str, Any]:
        textual = self._textual_config(create=create)
        last_used = textual.get("last_used", {})
        if not isinstance(last_used, dict):
            last_used = {}
            if create:
                textual["last_used"] = last_used
        elif create:
            textual["last_used"] = last_used
        return last_used

    def _textual_selection_presets_config(self, *, create: bool) -> Dict[str, Any]:
        textual = self._textual_config(create=create)
        presets = textual.get("selection_presets", {})
        if not isinstance(presets, dict):
            presets = {}
            if create:
                textual["selection_presets"] = presets
        elif create:
            textual["selection_presets"] = presets
        return presets

    def _capture_textual_selection_snapshot(self) -> Dict[str, Any]:
        snapshot: Dict[str, Any] = {}
        if self.active_mode is not None:
            snapshot["active_mode"] = self.active_mode.name
        elif self.active_agent_profile is not None:
            snapshot["active_profile"] = self.active_agent_profile.name
        if self.global_llm_override:
            snapshot["global_llm_profile"] = self.global_llm_override
        if self.enabled_skills:
            snapshot["skills"] = list(self.enabled_skills)
        session_default = self.session_confirmation_overrides.get("default_policy")
        if session_default is not None:
            snapshot["session_confirmation_default"] = session_default
        snapshot["auto_confirm_tools"] = bool(self.auto_confirm_tools)
        last_used = self._textual_last_used_config(create=False)
        agent_profiles = last_used.get("agent_profiles", {})
        if isinstance(agent_profiles, dict) and agent_profiles:
            snapshot["agent_profiles"] = copy.deepcopy(agent_profiles)
        return snapshot

    def _normalize_textual_selection_snapshot(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        snapshot: Dict[str, Any] = {}
        active_mode = str(raw.get("active_mode") or "").strip()
        if active_mode:
            snapshot["active_mode"] = active_mode
        active_profile = str(raw.get("active_profile") or "").strip()
        if active_profile:
            snapshot["active_profile"] = active_profile
        global_llm_profile = str(raw.get("global_llm_profile") or "").strip()
        if global_llm_profile:
            snapshot["global_llm_profile"] = global_llm_profile
        if isinstance(raw.get("skills"), list):
            snapshot["skills"] = self._normalize_skill_names(list(raw.get("skills", [])), strict=False)
        session_default = self._normalize_confirmation_policy(raw.get("session_confirmation_default"))
        if session_default is not None:
            snapshot["session_confirmation_default"] = session_default
        if "auto_confirm_tools" in raw:
            snapshot["auto_confirm_tools"] = bool(raw.get("auto_confirm_tools"))
        raw_agent_profiles = raw.get("agent_profiles", {})
        if isinstance(raw_agent_profiles, dict):
            cleaned_profiles: Dict[str, Any] = {}
            for profile_name, state in raw_agent_profiles.items():
                cleaned_name = str(profile_name).strip()
                if not cleaned_name or not isinstance(state, dict):
                    continue
                cleaned_state: Dict[str, Any] = {}
                if "tools" in state:
                    tools = state.get("tools")
                    cleaned_state["tools"] = self._normalize_tool_list(tools) if isinstance(tools, list) else None
                if "tool_confirmation_overrides" in state:
                    cleaned_state["tool_confirmation_overrides"] = self._normalized_confirmation_overrides(
                        state.get("tool_confirmation_overrides", {})
                    )
                if cleaned_state:
                    cleaned_profiles[cleaned_name] = cleaned_state
            if cleaned_profiles:
                snapshot["agent_profiles"] = cleaned_profiles
        return snapshot

    def _current_last_used_selection_snapshot(self) -> Dict[str, Any]:
        last_used = self._textual_last_used_config(create=False)
        if not isinstance(last_used, dict):
            return {}
        return self._normalize_textual_selection_snapshot(last_used)

    def _replace_last_used_selection_snapshot(self, snapshot: Dict[str, Any]) -> None:
        normalized = self._normalize_textual_selection_snapshot(snapshot)
        last_used = self._textual_last_used_config(create=True)
        for key in (
            "active_mode",
            "active_profile",
            "global_llm_profile",
            "skills",
            "session_confirmation_default",
            "auto_confirm_tools",
            "agent_profiles",
        ):
            if key in normalized:
                value = normalized[key]
                last_used[key] = copy.deepcopy(value) if isinstance(value, dict) else value
            else:
                last_used.pop(key, None)
        self.enabled_skills = self._normalize_skill_names(normalized.get("skills", []), strict=False)
        self._refresh_runtime_components()
        self._cleanup_textual_last_used_config()

    def _cleanup_invalid_textual_selection_presets(
        self,
        *,
        removed_profile: str | None = None,
        removed_llm: str | None = None,
        removed_mode: str | None = None,
    ) -> None:
        presets = self._textual_selection_presets_config(create=False)
        if not presets:
            return
        for preset_name, raw_snapshot in list(presets.items()):
            if not isinstance(raw_snapshot, dict):
                presets.pop(preset_name, None)
                continue
            snapshot = self._normalize_textual_selection_snapshot(raw_snapshot)
            if removed_profile:
                if snapshot.get("active_profile") == removed_profile:
                    snapshot.pop("active_profile", None)
                agent_profiles = snapshot.get("agent_profiles")
                if isinstance(agent_profiles, dict):
                    agent_profiles.pop(removed_profile, None)
                    if not agent_profiles:
                        snapshot.pop("agent_profiles", None)
            if removed_llm and snapshot.get("global_llm_profile") == removed_llm:
                snapshot.pop("global_llm_profile", None)
            if removed_mode and snapshot.get("active_mode") == removed_mode:
                snapshot.pop("active_mode", None)
            presets[preset_name] = snapshot

    def _textual_profile_state(self, profile_name: str, *, create: bool) -> Dict[str, Any]:
        last_used = self._textual_last_used_config(create=create)
        agent_profiles = last_used.get("agent_profiles", {})
        if not isinstance(agent_profiles, dict):
            agent_profiles = {}
            if create:
                last_used["agent_profiles"] = agent_profiles
        elif create:
            last_used["agent_profiles"] = agent_profiles
        profile_state = agent_profiles.get(profile_name, {})
        if not isinstance(profile_state, dict):
            profile_state = {}
            if create:
                agent_profiles[profile_name] = profile_state
        elif create:
            agent_profiles[profile_name] = profile_state
        return profile_state

    def _cleanup_textual_profile_state(self, profile_name: str) -> None:
        last_used = self._textual_last_used_config(create=False)
        agent_profiles = last_used.get("agent_profiles", {})
        if not isinstance(agent_profiles, dict):
            return
        profile_state = agent_profiles.get(profile_name)
        if isinstance(profile_state, dict) and not profile_state:
            agent_profiles.pop(profile_name, None)
        if not agent_profiles:
            last_used.pop("agent_profiles", None)
        self._cleanup_textual_last_used_config()

    def _cleanup_textual_last_used_config(self) -> None:
        textual = self._textual_config(create=False)
        last_used = textual.get("last_used", {})
        if isinstance(last_used, dict) and not last_used:
            textual.pop("last_used", None)

    def _configured_enabled_skills(self) -> List[str]:
        textual = self._textual_config(create=False)
        last_used = textual.get("last_used", {}) if isinstance(textual, dict) else {}
        if isinstance(last_used, dict) and isinstance(last_used.get("skills"), list):
            return self._normalize_skill_names(last_used.get("skills", []), strict=False)
        default_skills = textual.get("default_skills", []) if isinstance(textual, dict) else []
        return self._normalize_skill_names(default_skills, strict=False)

    def _normalize_skill_names(self, skill_names: List[str], *, strict: bool) -> List[str]:
        normalized: list[str] = []
        for raw_name in skill_names or []:
            skill_name = str(raw_name).strip()
            if not skill_name:
                continue
            if self._skill_manager.get(skill_name) is None:
                if strict:
                    raise ValueError(f"Unknown skill '{skill_name}'. Available: {self.list_skills()}")
                continue
            if skill_name not in normalized:
                normalized.append(skill_name)
        return normalized

    def _normalize_tool_list(self, tools: Optional[List[str]]) -> Optional[List[str]]:
        if tools is None:
            return None
        normalized: list[str] = []
        for raw_name in tools:
            tool_name = str(raw_name).strip()
            if tool_name and tool_name not in normalized:
                normalized.append(tool_name)
        return sorted(normalized)

    def _normalized_confirmation_overrides(self, overrides: Any) -> Dict[str, str]:
        if not isinstance(overrides, dict):
            return {}
        normalized: Dict[str, str] = {}
        for tool_name, policy in overrides.items():
            tool_key = str(tool_name).strip()
            if not tool_key:
                continue
            normalized_policy = self._normalize_confirmation_policy(policy)
            if normalized_policy is not None:
                normalized[tool_key] = normalized_policy
        return normalized

    def _base_agent_profile(self, name: str) -> Any:
        return self._agent_profile_manager.get(name)

    def _apply_textual_profile_overrides(self, profile: AgentProfile | None) -> AgentProfile | None:
        if profile is None:
            return None
        profile_state = self._textual_profile_state(profile.name, create=False)
        if not profile_state:
            return profile

        tools = list(profile.tools) if profile.tools is not None else None
        if "tools" in profile_state:
            raw_tools = profile_state.get("tools")
            tools = self._normalize_tool_list(raw_tools) if isinstance(raw_tools, list) else None

        confirmation = copy.deepcopy(profile.tool_confirmation or {})
        if "tool_confirmation_overrides" in profile_state:
            overrides = self._normalized_confirmation_overrides(profile_state.get("tool_confirmation_overrides", {}))
            if overrides:
                confirmation["overrides"] = overrides
            else:
                confirmation.pop("overrides", None)

        return dataclasses.replace(
            profile,
            tools=tools,
            extra_prompts=list(profile.extra_prompts),
            tool_confirmation=confirmation,
        )

    def _refresh_active_profile(self, profile_name: str) -> None:
        if self.active_agent_profile is None or self.active_agent_profile.name != profile_name:
            return
        raw_profile = self._base_agent_profile(profile_name)
        if raw_profile is None:
            return
        self.active_agent_profile = self._apply_textual_profile_overrides(raw_profile)

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
