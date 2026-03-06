# Plugin Architecture

PocketCoder plugins are self-contained directories that declare tools, prompts, and
flows in a single `plugin.yaml` manifest. Every resource is addressed by a
two-part qualified name: `plugin_name.resource_name`.

---

## Unified Plugin Model

As of the 003-unified-plugin-namespace release, all plugins share one manifest format
and one namespace. There are no separate workflow YAML files — flow logic is expressed
as a [PocketFlow](pocketflow_agents.md) `Flow` factory.

### Plugin Directory Layout

```
my_plugin/
├── plugin.yaml          # Required: unified manifest (schema_version: 1)
├── agents/
│   ├── __init__.py      # Empty package init
│   └── my_agent.py     # PocketFlow Node + Flow factory
├── prompts/
│   └── system.md       # Markdown system prompt
└── tools/
    └── my_tools.py     # BaseTool subclasses
```

---

## Plugin Manifest (`plugin.yaml`)

Every plugin **must** have a `plugin.yaml` with `schema_version: 1` as its first key.

```yaml
schema_version: 1
name: my_plugin
description: "What this plugin does."

tools:
  my_tool: "tools/my_tools.py:MyTool"

flows:
  my_agent:
    module: "agents/my_agent.py"
    entry_fn: "create_flow"
    description: "Flow that does X."
    tools: [my_tool]
    prompt_files: ["prompts/system.md"]   # `prompts:` is also accepted as an alias

prompts:
  system: "prompts/system.md"
```

| Key | Required | Description |
|-----|----------|-------------|
| `schema_version` | ✅ | Must be `1`. |
| `name` | Optional | Defaults to the directory name. |
| `description` | Optional | Human-readable summary. |
| `tools` | Optional | `local_name: "file.py:ClassName"` mappings. |
| `flows` | Optional | Flow blocks with `module` + `entry_fn`. |
| `prompts` | Optional | Top-level prompt registry entries: `local_name: "prompts/file.md"`. |

---

## Flow Factory (`agents/my_agent.py`)

Each flow is a zero-argument factory function that returns a PocketFlow `Flow`.

```python
from __future__ import annotations
from typing import Any, Dict
from pocketflow import Flow, Node

class MyThinkNode(Node):
    def prep(self, shared: Dict[str, Any]) -> str:
        return shared.get("task", "")

    def exec(self, task: str) -> str:
        return task                          # forward to LLM router if wired

    def post(self, shared, prep_res, exec_res) -> str:
        shared["result"] = exec_res
        return "continue"

def create_flow() -> Flow:
    return Flow(start=MyThinkNode())
```

Register the factory in `plugin.yaml` under `flows:`:

```yaml
flows:
  my_agent:
    module: "agents/my_agent.py"
    entry_fn: "create_flow"
    prompt_files: ["prompts/system.md"]
```

---

## Namespace & Qualified Names

Every resource is registered as `{plugin_name}.{local_name}`:

| Local reference | Qualified name | Resolves to |
|-----------------|----------------|-------------|
| `my_tool` (from `my_plugin`) | `my_plugin.my_tool` | `MyTool` impl |
| `my_agent` | `my_plugin.my_agent` | `FlowDefinition` with Flow |

Unqualified bare-name resolution:
- **Unique owner** → resolved with a `WARNING` suggesting qualification.
- **Multiple owners** → raises `RegistryError`; caller must qualify the name.

---

## Core Plugin (`pocketcode/plugins/core`)

The built-in `core` plugin ships all standard tools and three base flows:

| Qualified name | Description |
|----------------|-------------|
| `core.read_file` | Read a file from the workspace |
| `core.write_to_file` | Write content to a file |
| `core.search_code` | Search the codebase |
| `core.execute_command` | Run a shell command |
| `core.git_diff` | Show a git diff |
| `core.ask_user` | Prompt the user for input |
| `core.coder` | Code-writing flow |
| `core.architect` | Planning & architecture flow |
| `core.ask` | Clarification/question flow |

---

## Hot Reload

Plugin changes are detected by `PluginWatcher`. On any file-system event inside a
plugin directory, a new `PluginManager` snapshot is built and atomically swapped into
the `RegistryHolder` — live sessions transparently see the updated registry within
500 ms.

---

## Legacy `agent.yaml` Migration

Plugins that still use `agent.yaml` are loaded via a one-release compatibility shim
that emits `WARNING` log records and returns `schema_version=0`. They **will not** be
loaded as PocketFlow flows until migrated.

Migration steps:

1. Rename `agent.yaml` → `plugin.yaml`.
2. Add `schema_version: 1` as the first key.
3. Convert the `tools:` list to a `tools:` dict: `local_name: "file.py:Class"`.
4. Create an `agents/` directory with a `create_flow()` factory module.
5. Add a `flows:` block pointing to the factory.
6. Remove `workflows:`, `components:`, and `node_definitions:` legacy sections.

See [`specs/003-unified-plugin-namespace/quickstart.md`](../specs/003-unified-plugin-namespace/quickstart.md)
for a step-by-step walkthrough.
