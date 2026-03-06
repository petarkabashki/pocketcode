from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Agent:
    """A named configuration bundle that governs how a flow is invoked.

    Every flow has at least one agent: either explicitly declared in
    ``plugin.yaml`` under ``default_agent``, or synthesised from the
    flow's top-level fields by ``AgentManager``.

    Fields
    ------
    name : str
        Unique identifier (e.g. ``"core::react"`` or ``"react-safe"``).
    flow : str
        Qualified flow reference this agent targets (e.g. ``"core::react"``).
    description : str
        Human-readable description. Default ``""``.
    llm_profile : str | None
        LLM configuration profile name. ``None`` means inherit from lower tiers.
    extra_prompts : List[str]
        Ordered list of file paths whose contents are appended to the system
        prompt each turn. Default ``[]``.
    tools : List[str] | None
        Explicit tool allowlist (qualified names). ``None`` means inherit all.
    tool_confirmation : Dict[str, Any]
        ``{"default": str | None, "overrides": Dict[str, str]}``.
        Absent keys mean "no opinion at this tier". Default ``{}``.
    source : str
        Provenance: ``"synthesised"``, ``"plugin"``, or ``"workspace"``.
    source_path : Path | None
        Absolute path to the YAML file for workspace profiles. ``None`` for
        synthesised and plugin profiles.
    """

    name: str
    agent: str
    description: str = ""
    llm_profile: Optional[str] = None
    extra_prompts: List[str] = field(default_factory=list)
    tools: Optional[List[str]] = None
    tool_confirmation: Dict[str, Any] = field(default_factory=dict)
    source: str = "synthesised"
    source_path: Optional[Path] = None

    @property
    def flow(self) -> str:
        """Canonical alias for the target flow name."""
        return self.agent

    @flow.setter
    def flow(self, value: str) -> None:
        self.agent = value


@dataclass
class FlowDefinition:
    name: str
    description: str = ""
    llm_profile: str | None = None
    tools: List[str] = field(default_factory=list)
    handoff_agents: List[str] = field(default_factory=list)
    execution_mode: str = "llm"
    deterministic_handler: str | None = None
    composite_agents: List[str] = field(default_factory=list)
    system_prompt: str = ""
    prompt_sources: List[str] = field(default_factory=list)
    pre_handlers: List[str] = field(default_factory=list)
    step_handlers: List[str] = field(default_factory=list)
    post_handlers: List[str] = field(default_factory=list)
    handoff_policies: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    default_handoff_policy: Dict[str, Any] = field(default_factory=dict)
    is_programmatic: bool = False
    module: Optional[str] = None
    entry_fn: Optional[str] = None
    flow_instance: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    default_agent_profile: Optional[Agent] = None

    @property
    def default_agent(self) -> Optional[Agent]:
        """Canonical alias for the default runtime agent."""
        return self.default_agent_profile

    @default_agent.setter
    def default_agent(self, value: Optional[Agent]) -> None:
        self.default_agent_profile = value


AgentProfile = Agent
AgentDefinition = FlowDefinition
