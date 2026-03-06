"""AgentProfileManager — loads, indexes, and persists AgentProfile objects.

Load order (highest precedence first within same name):
  1. Plugin-declared (default_agent_profile block with explicit ``name`` field)
  2. Workspace-local file  (.pocketcode/agent-profiles/<name>.yaml)
  3. Synthesised default  (built from AgentDefinition top-level fields)

A WARNING is logged on any name collision, identifying both conflicting sources.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class AgentProfileManager:
    """Runtime registry for AgentProfile objects.

    Instantiated once by the engine; ``load()`` is called after every
    ``PluginManager.load()`` / ``engine.reload()`` cycle.
    """

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._workspace_profiles_dir: Path = self._workspace_root / ".pocketcode" / "agent-profiles"
        self._profiles: Dict[str, Any] = {}  # str -> AgentProfile
        self._agent_definitions: Dict[str, Any] = {}  # cached for reload / clone

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, agent_definitions: Dict[str, Any]) -> None:  # Dict[str, AgentDefinition]
        """Rebuild the profile registry from agent definitions + workspace files.

        Steps:
        1. Store agent_definitions for later use by clone()/reload().
        2. Clear _profiles.
        3. Register plugin-declared profiles (source="plugin"), then synthesise
           defaults for any agent that has no explicit default_agent_profile.
        4. Scan _workspace_profiles_dir/*.yaml alphabetically; register workspace
           profiles (source="workspace"), applying collision rules.
        """
        # Import here to avoid circular imports at module load time.
        from pocketcode.core.runtime_models import AgentProfile  # noqa: PLC0415

        self._agent_definitions = dict(agent_definitions)
        self._profiles = {}

        # Step 3: plugin-declared (highest precedence) then synthesised defaults
        for qname, defn in agent_definitions.items():
            explicit: Optional[AgentProfile] = getattr(defn, "default_agent_profile", None)
            if explicit is not None:
                # Plugin declared an explicit profile; use it directly.
                self._register(explicit, collision_source="plugin-declared")
            else:
                # Synthesise from top-level agent fields.
                synth = AgentProfile(
                    name=qname,
                    agent=qname,
                    description=f"Synthesised default profile for {qname}.",
                    llm_profile=getattr(defn, "llm_profile", None),
                    extra_prompts=[],
                    tools=list(getattr(defn, "tools", None) or []) or None,
                    tool_confirmation={},
                    source="synthesised",
                    source_path=None,
                )
                # A synthesised list of tools that equals the full list is
                # effectively "no restriction", so store as None.
                if synth.tools == []:
                    synth.tools = None
                self._register(synth, collision_source="synthesised")

        # Step 4: workspace YAML files — lowest precedence per explicit name,
        #         but can override synthesised defaults.
        self._load_workspace_files()

    def get(self, name: str) -> Optional[Any]:  # -> AgentProfile | None
        """Return a profile by name, or None if not found."""
        return self._profiles.get(name)

    def list(self) -> List[Any]:  # List[AgentProfile]
        """Return all profiles sorted by name."""
        return sorted(self._profiles.values(), key=lambda p: p.name)

    def clone(self, src_name: str, new_name: str) -> Any:  # -> AgentProfile
        """Clone *src_name* to *new_name*.

        Creates ``.pocketcode/agent-profiles/<new_name>.yaml``,
        reloads the registry, and returns the new profile.

        Raises:
            ValueError: if ``src_name`` not found or ``new_name`` file already exists.
        """
        from pocketcode.core.runtime_models import AgentProfile  # noqa: PLC0415
        import dataclasses  # noqa: PLC0415

        src: Optional[AgentProfile] = self.get(src_name)
        if src is None:
            raise ValueError(
                f"Cannot clone: source profile '{src_name}' not found. "
                f"Available: {[p.name for p in self.list()]}"
            )

        target_path = self._workspace_profiles_dir / f"{new_name}.yaml"
        if target_path.exists():
            raise ValueError(
                f"Cannot clone: target file '{target_path}' already exists. "
                "Choose a different name or remove the existing file first."
            )

        new_profile = dataclasses.replace(
            src,
            name=new_name,
            source="workspace",
            source_path=target_path,
        )
        self.save(new_profile)
        self.reload(self._agent_definitions)
        return self.get(new_name)  # type: ignore[return-value]

    def save(self, profile: Any) -> None:  # profile: AgentProfile
        """Serialise *profile* to its ``source_path`` on disk.

        Auto-creates ``_workspace_profiles_dir`` if it does not exist.
        """
        if profile.source_path is None:
            raise ValueError(
                f"Profile '{profile.name}' has no source_path; cannot save. "
                "Use clone() to promote a profile to a workspace file."
            )
        self._workspace_profiles_dir.mkdir(parents=True, exist_ok=True)
        data = self._profile_to_yaml_dict(profile)
        profile.source_path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        logger.debug("Saved agent profile '%s' to %s", profile.name, profile.source_path)

    def reload(self, agent_definitions: Dict[str, Any]) -> None:
        """Alias for load() — called after plugin reload or clone."""
        self.load(agent_definitions)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _register(self, profile: Any, collision_source: str) -> None:
        """Register a profile, logging a WARNING on name collision."""
        existing = self._profiles.get(profile.name)
        if existing is not None:
            # Determine precedence: plugin-declared > workspace > synthesised
            precedence = {"plugin": 3, "synthesised": 1, "workspace": 2}
            incoming_rank = precedence.get(profile.source, 0)
            existing_rank = precedence.get(existing.source, 0)

            logger.warning(
                "Agent profile name collision for '%s': "
                "existing source='%s', incoming source='%s' (%s). "
                "%s wins.",
                profile.name,
                existing.source,
                profile.source,
                collision_source,
                "Existing" if existing_rank >= incoming_rank else "Incoming",
            )
            if incoming_rank > existing_rank:
                self._profiles[profile.name] = profile
        else:
            self._profiles[profile.name] = profile

    def _load_workspace_files(self) -> None:
        """Scan _workspace_profiles_dir/*.yaml alphabetically, register each."""
        from pocketcode.core.runtime_models import AgentProfile  # noqa: PLC0415

        if not self._workspace_profiles_dir.exists():
            return

        for yaml_file in sorted(self._workspace_profiles_dir.glob("*.yaml")):
            try:
                raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
                if not isinstance(raw, dict):
                    logger.warning(
                        "Skipping agent profile file '%s': root must be a YAML mapping.", yaml_file
                    )
                    continue

                name = raw.get("name")
                agent = raw.get("agent")
                if not name:
                    logger.warning(
                        "Skipping agent profile file '%s': missing required field 'name'.", yaml_file
                    )
                    continue
                if not agent:
                    logger.warning(
                        "Skipping agent profile file '%s': missing required field 'agent'.", yaml_file
                    )
                    continue

                tool_confirmation_raw = raw.get("tool_confirmation", {})
                if not isinstance(tool_confirmation_raw, dict):
                    tool_confirmation_raw = {}

                tools_raw = raw.get("tools")  # None or List[str]
                if tools_raw is not None and not isinstance(tools_raw, list):
                    tools_raw = None

                profile = AgentProfile(
                    name=str(name),
                    agent=str(agent),
                    description=str(raw.get("description", "")),
                    llm_profile=str(raw["llm_profile"]) if raw.get("llm_profile") else None,
                    extra_prompts=[str(p) for p in raw.get("extra_prompts", []) if isinstance(p, str)],
                    tools=[str(t) for t in tools_raw if isinstance(t, str)] if tools_raw is not None else None,
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
                    source="workspace",
                    source_path=yaml_file.resolve(),
                )
                self._register(profile, collision_source=str(yaml_file))

            except yaml.YAMLError as exc:
                logger.warning(
                    "Skipping agent profile file '%s': invalid YAML — %s", yaml_file, exc
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Skipping agent profile file '%s': unexpected error — %s", yaml_file, exc
                )

    @staticmethod
    def _profile_to_yaml_dict(profile: Any) -> Dict[str, Any]:
        """Convert an AgentProfile to a YAML-serialisable dict (workspace file schema)."""
        tool_confirmation: Dict[str, Any] = {}
        raw_tc = profile.tool_confirmation or {}
        default_policy = raw_tc.get("default")
        overrides = raw_tc.get("overrides") or {}
        if default_policy:
            tool_confirmation["default"] = default_policy
        if overrides:
            tool_confirmation["overrides"] = dict(overrides)

        data: Dict[str, Any] = {
            "name": profile.name,
            "agent": profile.agent,
        }
        if profile.description:
            data["description"] = profile.description
        if profile.llm_profile:
            data["llm_profile"] = profile.llm_profile
        if profile.tools is not None:
            data["tools"] = list(profile.tools)
        if profile.extra_prompts:
            data["extra_prompts"] = list(profile.extra_prompts)
        if tool_confirmation:
            data["tool_confirmation"] = tool_confirmation
        return data
