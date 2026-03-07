# PocketFlow Agents

PocketCoder agents are expressed as PocketFlow `Flow` factories registered in
`plugin.yaml`. This replaces the older YAML-workflow and `agent.yaml` formats
completely — agents ARE flows, with no separate workflow layer.

This authoring terminology is internal to plugin and flow design. The public CLI
uses agent-centered command and status wording, while interface-specific command
discovery stays local to the interface that owns it.

---

## Overview

A PocketFlow agent is a Python module that contains:

1. One or more `Node` subclasses (each node is a step in the agent's reasoning loop).
2. A `create_flow() -> Flow` factory function that wires the nodes into a `Flow` and
   returns it.

The `Flow` is then referenced from `plugin.yaml` via `module:` + `entry_fn:`.

---

## Creating an Agent

### 1. Define Nodes

```python
from pocketflow import Node
from typing import Any, Dict

class ThinkNode(Node):
    def prep(self, shared: Dict[str, Any]) -> str:
        """Extract the task from shared state."""
        return shared.get("task", "")

    def exec(self, task: str) -> str:
        """Pure computation step — no shared state side-effects here."""
        return task  # hand off to LLM router when wired

    def post(self, shared: Dict[str, Any], prep_res: str, exec_res: str) -> str:
        """Update shared state and return an action string for branching."""
        shared["result"] = exec_res
        return "continue"  # matches a transition key defined in the Flow
```

### 2. Wire into a Flow

```python
from pocketflow import Flow

def create_flow() -> Flow:
    think = ThinkNode()
    # Simple single-node flow:
    return Flow(start=think)
```

For multi-step agents, connect nodes with the `>>` operator:

```python
def create_flow() -> Flow:
    plan = PlanNode()
    execute = ExecuteNode()
    review = ReviewNode()

    plan >> {"execute": execute, "done": None}
    execute >> {"review": review, "retry": execute}
    review >> {"done": None, "revise": execute}

    return Flow(start=plan)
```

### 3. Register in `plugin.yaml`

```yaml
schema_version: 1
name: my_plugin
description: My plugin.

flows:
  my_agent:
    module: "flows/my_agent.py"
    entry_fn: "create_flow"
    description: "Does X using Y."
    tools: [my_tool]
    prompt_files: ["prompts/system.md"]
```

---

## Shared Store (`shared`)

The `shared` dictionary is the single mutable context passed between all nodes in a
session. Useful keys injected by the runtime:

| Key | Type | Description |
|-----|------|-------------|
| `"task"` | `str` | Initial user request |
| `"messages"` | `list` | Conversation history |
| `"_registry"` | `PluginManager` | Live plugin registry snapshot |
| `"_llm_router"` | `LLMRouter` | LLM routing client (if wired) |
| `"results"` | `dict` | Accumulated outputs |

---

## Cross-Flow Delegation

An orchestrating flow (e.g., `micromanager`) can delegate to other flows by
resolving their `FlowDefinition` from `shared["_registry"]`:

```python
def post(self, shared, prep_res, exec_res):
    registry = shared.get("_registry")
    try:
        flow_def = registry.agents.resolve("coder::coder")
        flow_def.flow_instance.run(shared)
    except Exception as exc:
        shared["error"] = str(exc)
    return "done"
```

---

## Architecture Notes

- Flows supersede workflows: there is no separate `workflows:` YAML — the `Flow`
  graph IS the workflow.
- `flow_instance` is eagerly created at plugin-load time by calling `entry_fn()`.
  If the factory raises, the flow is skipped and `ERROR` is logged.
- All flows are addressed by their qualified name `{plugin}.{flow}` in the
  `NamespaceRegistry`.

See [Plugin Architecture](plugin_architecture.md) for the full plugin model.
See [`specs/003-unified-plugin-namespace/quickstart.md`](../specs/003-unified-plugin-namespace/quickstart.md)
for an end-to-end walkthrough of creating a new plugin.
