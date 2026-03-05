from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AgentDefinition:
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
    metadata: Dict[str, Any] = field(default_factory=dict)
