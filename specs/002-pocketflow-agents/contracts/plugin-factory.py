# Contract: Plugin Factory 

**Feature**: [002-pocketflow-agents](../spec.md)
**Date**: 2026-03-05

## 1. Plugin Class Interface (pocketcode.core.interfaces)
```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Union
from pocketflow import Flow, AsyncFlow

@dataclass
class Plugin:
    """Standard container for plugin resources."""
    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    tools: List[Callable] = field(default_factory=list)
    prompts: Dict[str, str] = field(default_factory=dict)
    agents: Dict[str, Union[Flow, AsyncFlow]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

## 2. Factory Function Signature
Each plugin's `__init__.py` (or a designated entry point) should implement this function:

```python
def get_plugin(config: Dict[str, Any]) -> Plugin:
    """
    Initializes and returns the Plugin container.
    Args:
        config: Global settings and plugin-specific configuration.
    Returns:
        Plugin: An initialized container instance.
    """
    # ... plugin setup logic ...
    return Plugin(name="my-plugin", ...)
```

## 3. Storage & Configuration (PluginContext)
```python
class PluginContext:
    """Passed to each Flow in shared['_plugin']."""
    def __init__(self, plugin: Plugin, runtime: Any):
        self.name = plugin.name
        self.tools = {t.__name__: t for t in plugin.tools}
        self.prompts = plugin.prompts
        self._runtime = runtime

    def get_prompt(self, name: str) -> str:
        """Retrieve a local prompt by name."""
        return self.prompts.get(name, "")

    def call_tool(self, name: str, **kwargs) -> Any:
        """Call a plugin-local tool."""
        # ... logic to invoke with the current runtime ...
        pass
```
