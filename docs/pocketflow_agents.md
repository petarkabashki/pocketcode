# Programming Agent with PocketFlow

PocketCoder supports defining agent logic programmatically using [PocketFlow](pocketflow.md). This approach provides full control over the agent's behavior, branching, and tool usage without relying on YAML/Markdown workflow descriptions.

## Overview

A programmatic agent is defined in the plugin's `agent.py` file using PocketFlow's `Node` and `Flow` classes. These agents are registered via a factory function in the plugin's `__init__.py`.

## Creating a Programmatic Agent

### 1. Define Nodes

Nodes represent individual steps in your agent's workflow. Inherit from `pocketflow.Node` and implement the `_run` method.

```python
from pocketcode.core.pocketflow import Node

class MyNode(Node):
    def _run(self, shared):
        # Access the plugin context injected by the runtime
        ctx = shared.get("_plugin")
        
        # Call a tool registered in this plugin (or globally)
        result = ctx.call_tool("my_tool", arg1="value")
        
        # Load a prompt from the plugin's prompts/ directory
        system_prompt = ctx.get_prompt("system")
        
        # Update shared state
        shared["last_result"] = result
        
        # Return an action string for branching
        return "success"
```

### 2. Define the Flow

The `Flow` class orchestrates the execution of nodes.

```python
from pocketcode.core.pocketflow import Flow

class MyAgentFlow(Flow):
    def __init__(self):
        super().__init__()
        self.start_node = MyNode()
        # Define transitions: node >> { "action": next_node }
        # or simply node >> next_node for default transitions
```

### 3. Register via Factory

In your plugin's `__init__.py`, define a `get_plugin()` function that returns a `Plugin` instance containing your agent.

```python
from pocketcode.core.interfaces import Plugin
from .agent import MyAgentFlow
from .tools.my_tools import my_tool

def get_plugin():
    return Plugin(
        name="my-plugin",
        tools=[my_tool],
        agents={
            "my-agent": MyAgentFlow()
        }
    )
```

## PluginContext API

When a programmatic agent runs, a `PluginContext` object is automatically injected into `shared["_plugin"]`. It provides the following methods:

- `call_tool(tool_name: str, **kwargs)`: Executes a tool by name. Handles both local plugin tools and global tools.
- `get_prompt(prompt_name: str) -> str`: Retrieves the content of a prompt file from the plugin's `prompts/` directory (e.g., `prompts/system.md`).
- `name`: The name of the plugin.

## Running the Agent

Use the `--agent` flag with the CLI:

```bash
python -m pocketcode.main --agent my-agent --prompt "Your request"
```

## Best Practices

1. **State Management**: Use the `shared` dictionary to pass data between nodes.
2. **Error Handling**: Use node transitions to handle failures (e.g., `node >> {"error": recovery_node}`).
3. **Local Tools**: Prefer defining tools within the plugin and registering them via the factory for better encapsulation.
