# Quickstart: Unified Plugin Namespace — Plugin Author Guide

**Date**: 2026-03-05 | **Feature**: 003-unified-plugin-namespace

This guide shows how to create, migrate, and reference resources under the new unified plugin namespace model. Everything lives in one directory per plugin; every resource is owned by its plugin and addressable as `plugin_name.resource_name`.

---

## 1. Directory Layout for a New Plugin

```
pocketcode/plugins/my_plugin/
├── plugin.yaml              ← unified manifest (schema_version: 1)
├── tools/
│   └── my_tool.py           ← tool implementation(s)
├── agents/
│   └── my_agent.py          ← PocketFlow Flow factory
└── prompts/
    └── system.md            ← prompt content
```

No files outside this directory need to be created or modified.

---

## 2. Writing the Manifest (`plugin.yaml`)

```yaml
schema_version: 1             # REQUIRED — must be first key; integer 1
name: my_plugin               # must be unique across all loaded plugins
description: My custom plugin for demonstration.

tools:
  my_tool: tools/my_tool.py:MyTool        # file-relative reference
  shared_helper: tools/my_tool.py:HelperTool

agents:
  my_agent:
    description: A simple LLM-powered agent.
    module: agents/my_agent.py             # path relative to plugin root
    entry_fn: create_flow                  # zero-arg factory returning PocketFlow Flow
    llm_profile: gemini_default
    tools:
      - my_tool                            # local name — resolved within this plugin first
      - core.read_file                     # qualified cross-plugin reference
    prompts:
      system: prompts/system.md

prompts:
  system: prompts/system.md

llm_profiles:
  gemini_default:
    provider: gemini
    model: gemini-2.0-flash
```

**Rules**:
- `schema_version: 1` must appear; absence is a hard error — plugin is skipped.
- `tools` values: `path/to/file.py:ClassName` (file-relative) or `dotted.module.ClassName` (importable).
- Every `agents:` entry must have both `module:` and `entry_fn:`.
- Local tool/prompt names (no dot) are resolved within this plugin first, then globally.
- Qualified references (`plugin.name`) resolve unambiguously across all loaded plugins.

---

## 3. Writing a Tool

```python
# pocketcode/plugins/my_plugin/tools/my_tool.py
from pocketcode.core.interfaces import BaseTool


class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something useful."

    def execute(self, **kwargs) -> str:
        return "result"
```

No registration code needed anywhere else. Adding the tool to `plugin.yaml` is the only required step.

---

## 4. Writing an Agent (PocketFlow Factory)

```python
# pocketcode/plugins/my_plugin/agents/my_agent.py
from pocketflow import Flow, Node
from pocketcode.core.llm_factory import create_llm_client


class ThinkNode(Node):
    def prep(self, shared):
        return shared.get("task", "")

    def exec(self, task):
        llm = create_llm_client(shared_profile="gemini_default")
        return llm.generate(f"Complete this task: {task}")

    def post(self, shared, prep_res, exec_res):
        shared["result"] = exec_res
        # return None → "default" action → Flow ends


def create_flow() -> Flow:
    """Zero-argument factory — MUST return a PocketFlow Flow."""
    think = ThinkNode()
    return Flow(start=think)
```

The factory name (`create_flow`) must match `entry_fn:` in the manifest.

---

## 5. Writing an Orchestrating Agent (Multi-Agent Pipeline)

An orchestrating agent is architecturally identical to any other agent — it is a `Flow` whose nodes delegate to other agents as nested sub-flows.

```python
# pocketcode/plugins/my_plugin/agents/orchestrator.py
from pocketflow import Flow, Node


class DelegateNode(Node):
    """Delegates to another agent by resolving it from the registry."""

    def prep(self, shared):
        # The registry snapshot is passed in shared["_registry"] by the runtime
        registry = shared.get("_registry")
        sub_agent_def = registry.agents.resolve("core.Coder")
        return sub_agent_def.flow_instance

    def exec(self, sub_flow):
        return sub_flow  # pass to post for running

    def post(self, shared, prep_res, exec_res):
        exec_res.run(shared)


def create_flow() -> Flow:
    delegate = DelegateNode()
    return Flow(start=delegate)
```

Then in `plugin.yaml`:
```yaml
agents:
  orchestrator:
    module: agents/orchestrator.py
    entry_fn: create_flow
    description: Delegates to Coder for implementation tasks.
```

---

## 6. Referencing Resources Across Plugins

| Reference style | When to use | Example |
|---|---|---|
| Local name (no dot) | Within your own plugin | `my_tool`, `system` |
| Qualified name | Cross-plugin or disambiguation | `core.read_file`, `core.Coder` |

Local names are resolved within the owning plugin first (FR-004). Unqualified references to resources owned by exactly one *other* plugin emit a `WARNING` and are resolved; references matching resources in multiple plugins emit an `ERROR`.

**Avoid** bare names in cross-plugin contexts — always use qualified form:
```yaml
tools:
  - core.read_file      # ✓ unambiguous
  - read_file           # ✗ emits WARNING; will become an ERROR in future release
```

---

## 7. Migrating a Legacy `agent.yaml` Plugin

The system will load your `agent.yaml` for one release cycle while emitting a `WARNING` with migration steps. Full migration:

1. Rename `agent.yaml` → `plugin.yaml`.
2. Add `schema_version: 1` as the first key.
3. Move `personality.system_prompt` file path → `prompts.system:` entry.
4. Convert `tools:` list of `{id, handler}` dicts → `tools:` dict of `name: file.py:Class`.
5. Create an `agents:` block with `module:` + `entry_fn:` pointing to a Python factory returning a PocketFlow `Flow`.
6. Remove the `workflows:` list — express execution logic as a PocketFlow `Flow` in step 5.

**Example — before (`agent.yaml`)**:
```yaml
name: coder
personality:
  system_prompt: prompts/system.md
tools:
  - id: write_to_file
    handler: filesystem.py:WriteToFileTool
workflows:
  - id: default
    file: main.md
```

**After (`plugin.yaml`)**:
```yaml
schema_version: 1
name: coder
description: Expert developer.

tools:
  write_to_file: tools/filesystem.py:WriteToFileTool

agents:
  coder:
    module: agents/coder_agent.py
    entry_fn: create_flow
    llm_profile: gemini_default
    tools:
      - write_to_file
      - core.read_file
    prompts:
      system: prompts/system.md

prompts:
  system: prompts/system.md
```

---

## 8. Checking What's Registered

At runtime (e.g., in a debugging session or test):

```python
from pocketcode.core.engine import get_engine

engine = get_engine()
pm = engine.registry_holder.get()

# All tools
print(pm.tools.list_all())          # ['core.execute_command', 'core.git_add', ...]

# Tools by plugin
print(pm.tools.list_by_plugin("core"))

# Resolve a tool
tool_impl = pm.tools.resolve("core.read_file")

# All plugins
print(pm.tools.plugins())           # ['core', 'coder', ...]
```

---

## 9. Hot-Reload Behaviour

Modifying any file inside a plugin directory triggers an automatic reload (≤ 5 s):
- A new `PluginManager` snapshot is built from scratch.
- The active registry reference is atomically swapped.
- Sessions running at reload time complete using the pre-reload snapshot.
- Sessions started after the swap use the updated registrations.

No process restart needed. If a manifest has a `ManifestSchemaError`, the plugin is skipped and the error is logged; all other plugins continue loading normally.
