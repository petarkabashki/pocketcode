from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


HOOK_PHASES = (
    "before_turn",
    "before_llm",
    "after_llm",
    "before_tool",
    "after_tool",
    "after_turn",
)


@dataclass
class AgentCommand:
    name: str
    target: str
    target_kind: str = "command"
    target_agent: str | None = None
    target_visibility: str | None = None
    target_handler: str | None = None
    visibility: str = "exported"
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    payload_schema: Dict[str, Any] = field(default_factory=dict)
    result_schema: Dict[str, Any] = field(default_factory=dict)
    policy: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HookDefinition:
    name: str
    description: str = ""
    phases: Dict[str, str] = field(default_factory=dict)
    source: str = "workspace"
    source_path: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompositeAgent:
    """A named configuration bundle that governs how a flow is invoked.

    Every flow has at least one agent: either explicitly declared in
    flow metadata, loaded from a workspace or package resource-root
    ``*.agent.*`` file, or synthesised from the flow's top-level fields by
    the composite agent registry.

    Fields
    ------
    name : str
        Unique identifier (e.g. ``"core.react"`` or ``"react-safe"``).
    flow : str
        Qualified flow reference this agent targets (e.g. ``"core.react"``).
    base_agent : str | None
        Optional parent agent/profile name to inherit from. ``None`` means this
        agent resolves directly against its target flow.
    description : str
        Human-readable description. Default ``""``.
    llm_profile : str | None
        LLM configuration profile name. ``None`` means inherit from lower tiers.
    inline_prompt : str
        Inline system prompt text appended before any ``extra_prompts`` content.
        Used by named agents and other ephemeral runtime overlays.
    extra_prompts : List[str]
        Ordered list of file paths whose contents are appended to the system
        prompt each turn. Default ``[]``.
    hooks : List[str] | None
        Ordered list of hook asset references mixed into the profile.
    skills : List[str] | None
        Default enabled skill names for this profile. ``None`` means fall back
        to global Textual skill defaults.
    tools : List[str] | None
        Explicit tool allowlist (qualified names). ``None`` means inherit all.
    commands : List[AgentCommand]
        Declarative command aliases exported by this agent.
    tool_confirmation : Dict[str, Any]
        ``{"default": str | None, "overrides": Dict[str, str]}``.
        Absent keys mean "no opinion at this tier". Default ``{}``.
    source : str
        Provenance: ``"synthesised"``, ``"namespace"``, or ``"workspace"``.
        ``"namespace"`` marks synthesized overlays backed by configured
        namespace roots and non-workspace resource roots.
    source_path : Path | None
        Absolute path to the flat Markdown or YAML profile file. ``None`` for
        synthesised and non-workspace resource-root-backed agents.
    """

    name: str
    flow: str
    base_agent: Optional[str] = None
    description: str = ""
    llm_profile: Optional[str] = None
    inline_prompt: str = ""
    extra_prompts: List[str] = field(default_factory=list)
    hooks: Optional[List[str]] = None
    skills: Optional[List[str]] = None
    tools: Optional[List[str]] = None
    commands: List[AgentCommand] = field(default_factory=list)
    tool_confirmation: Dict[str, Any] = field(default_factory=dict)
    source: str = "synthesised"
    source_path: Optional[Path] = None

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
    vm_entry: Optional[str] = None
    vm_module: Optional[str] = None
    vm_modules: List[str] = field(default_factory=list)
    vm_module_prefixes: Dict[str, str] = field(default_factory=dict)
    vm_file: Optional[str] = None
    vm_files: List[str] = field(default_factory=list)
    vm_source: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    default_agent_profile: Optional[CompositeAgent] = None

    @property
    def default_agent(self) -> Optional[CompositeAgent]:
        """Canonical alias for the default runtime agent."""
        return self.default_agent_profile

    @default_agent.setter
    def default_agent(self, value: Optional[CompositeAgent]) -> None:
        self.default_agent_profile = value


Agent = CompositeAgent
AgentProfile = CompositeAgent
AgentDefinition = FlowDefinition
