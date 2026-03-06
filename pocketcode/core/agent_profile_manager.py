"""AgentManager — loads, indexes, and persists Agent objects.

Load order (highest precedence first within same name):
  1. Plugin-declared (default_agent block with explicit ``name`` field)
  2. Workspace-local file  (.pocketcode/agents/<name>.yaml)
  3. Synthesised default  (built from FlowDefinition top-level fields)

A WARNING is logged on any name collision, identifying both conflicting sources.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class AgentManager:
    """Runtime registry for Agent objects."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._workspace_agents_dir: Path = self._workspace_root / ".pocketcode" / "agents"
        self._legacy_workspace_agents_dir: Path = self._workspace_root / ".pocketcode" / "agent-profiles"
        self._agents: Dict[str, Any] = {}
        self._flow_definitions: Dict[str, Any] = {}

    def load(self, flow_definitions: Dict[str, Any]) -> None:
        """Rebuild the agent registry from flow definitions + workspace files."""
        from pocketcode.core.runtime_models import Agent  # noqa: PLC0415

        self._flow_definitions = dict(flow_definitions)
        self._agents = {}

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
                agent=qname,
                description=f"Synthesised default agent for {qname}.",
                llm_profile=getattr(defn, "llm_profile", None),
                extra_prompts=[],
                tools=list(getattr(defn, "tools", None) or []) or None,
                tool_confirmation={},
                source="synthesised",
                source_path=None,
            )
            if synth.tools == []:
                synth.tools = None
            self._register(synth, collision_source="synthesised")

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

    def _load_workspace_files(self) -> None:
        from pocketcode.core.runtime_models import Agent  # noqa: PLC0415

        yaml_files: List[Path] = []
        if self._legacy_workspace_agents_dir.exists():
            yaml_files.extend(sorted(self._legacy_workspace_agents_dir.glob("*.yaml")))
        if self._workspace_agents_dir.exists():
            yaml_files.extend(sorted(self._workspace_agents_dir.glob("*.yaml")))

        for yaml_file in yaml_files:
            try:
                raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
                if not isinstance(raw, dict):
                    logger.warning(
                        "Skipping agent file '%s': root must be a YAML mapping.", yaml_file
                    )
                    continue

                name = raw.get("name")
                flow = raw.get("flow") or raw.get("agent")
                if not name:
                    logger.warning(
                        "Skipping agent file '%s': missing required field 'name'.", yaml_file
                    )
                    continue
                if not flow:
                    logger.warning(
                        "Skipping agent file '%s': missing required field 'flow'.", yaml_file
                    )
                    continue

                tool_confirmation_raw = raw.get("tool_confirmation", {})
                if not isinstance(tool_confirmation_raw, dict):
                    tool_confirmation_raw = {}

                tools_raw = raw.get("tools")
                if tools_raw is not None and not isinstance(tools_raw, list):
                    tools_raw = None

                agent = Agent(
                    name=str(name),
                    agent=str(flow),
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
            tool_confirmation["overrides"] = dict(overrides)

        data: Dict[str, Any] = {
            "name": agent.name,
            "flow": agent.flow,
        }
        if agent.description:
            data["description"] = agent.description
        if agent.llm_profile:
            data["llm_profile"] = agent.llm_profile
        if agent.tools is not None:
            data["tools"] = list(agent.tools)
        if agent.extra_prompts:
            data["extra_prompts"] = list(agent.extra_prompts)
        if tool_confirmation:
            data["tool_confirmation"] = tool_confirmation
        return data


AgentProfileManager = AgentManager
