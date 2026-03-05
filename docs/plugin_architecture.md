# Plugin Architecture

Plugins in PocketCoder are modular components that provide tools, prompts, and agents.

## New Programmatic Structure (Recommended)

As of version 0.2.0, plugins can now be defined programmatically using a factory function and [PocketFlow Agents](pocketflow_agents.md).

### 1. Plugin Directory Structure
```
my_plugin/
├── __init__.py      # Factory function `get_plugin()`
├── agent.py        # PocketFlow nodes and flows
├── prompts/        # Markdown prompt templates
│   └── system.md
└── tools/          # Python tool implementations
    └── filesystem.py
```

### 2. Factory Function (`__init__.py`)
The `get_plugin()` function is the entry point for the plugin. It returns a `Plugin` object containing all resources.

```python
from pocketcode.core.interfaces import Plugin
from .agent import MyAgentFlow
from .tools.filesystem import read_local_file

def get_plugin():
    return Plugin(
        name="my-plugin",
        tools=[read_local_file],
        agents={"my-agent": MyAgentFlow()}
    )
```

## Legacy Configuration (YAML-based)
Traditional plugins use `agent.yaml` to define tools and workflows. While still supported, programmatic agents are preferred for complex logic.
