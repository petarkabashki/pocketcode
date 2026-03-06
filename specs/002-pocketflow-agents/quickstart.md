# Quickstart: PocketFlow Agents and Plugin Factory

**Feature**: [002-pocketflow-agents](../spec.md)
**Date**: 2026-03-05

This guide shows you how to migrate your agent from a YAML-based `workflow.md` description to a programmatic `pocketflow.Flow` using the new Plugin Factory model.

---

## 1. Create the Plugin Module
The plugin must be a Python package (a directory with an `__init__.py`).

```text
.pocketcode/plugins/my_new_agent/
├── __init__.py
├── agents.py
├── tools.py
└── prompts/
    └── system.md
```

## 2. Define the Plugin Factory
In `.pocketcode/plugins/my_new_agent/__init__.py`, implement `get_plugin(**config)`:

```python
from pocketcode.core.interfaces import Plugin
from .agents import HelloWorldFlow
from .tools import hello_tool

def get_plugin(config):
    """Factory function for Plugin initialization."""
    return Plugin(
        name="my-first-agent",
        description="A simple programmatic agent.",
        tools=[hello_tool],
        agents={"hello": HelloWorldFlow()},
        prompts={"system": "You are a helpful assistant."}
    )
```

## 3. Create the Flow
In `.pocketcode/plugins/my_new_agent/agents.py`, define your agent using `pocketflow`:

```python
from pocketflow import Flow, Node
from typing import Dict, Any

class ProcessNode(Node):
    def exec(self, prep_res):
        # Access plugin context and prompts from the shared dictionary
        ctx = self.shared["_plugin"]
        system_prompt = ctx.get_prompt("system")
        
        # Call a local tool
        result = ctx.call_tool("hello_tool", name="Copilot")
        return "success"

class HelloWorldFlow(Flow):
    def __init__(self):
        super().__init__()
        process = ProcessNode()
        self.start(process)
```

## 4. Run your Agent
Once the plugin directory is added to the `pocketcode.yml` configuration (or is in the default `.pocketcode/plugins/` directory), you can run it via the CLI:

```bash
python3 -m pocketcode.main --agent my-first-agent --prompt "Say hello"
```

The system will now call your `get_plugin()` function and execute the `HelloWorldFlow`.
