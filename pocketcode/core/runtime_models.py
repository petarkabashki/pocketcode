from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List


@dataclass
class ComponentDefinition:
    name: str
    kind: str
    plugin_name: str
    plugin_root: Path
    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentDefinition:
    name: str
    description: str = ""
    llm_profile: str | None = None
    tools: List[str] = field(default_factory=list)
    handoff_agents: List[str] = field(default_factory=list)
    system_prompt: str = ""
    prompt_sources: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowNodeDefinition:
    node_id: str
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowEdgeDefinition:
    source: str
    target: str
    transition: str = "default"
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowDefinition:
    name: str
    description: str
    plugin_name: str
    plugin_root: Path
    markdown_path: Path
    start_node: str
    default_agent: str | None
    workflow_kind: str = "graph"
    custom_flow: Any | None = None
    nodes: Dict[str, WorkflowNodeDefinition] = field(default_factory=dict)
    edges: List[WorkflowEdgeDefinition] = field(default_factory=list)
    prompt: str = ""
    prompt_sources: List[str] = field(default_factory=list)
    pre_handlers: List[str] = field(default_factory=list)
    step_handlers: List[str] = field(default_factory=list)
    post_handlers: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CustomNodeHandlerDefinition:
    kind: str
    handler: Callable[..., Any]
    plugin_name: str
    metadata: Dict[str, Any] = field(default_factory=dict)
