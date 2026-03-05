# Contract: Plugin Agent Manifest (`plugin.yaml` — `agents` section)

**Branch**: `004-agents-to-plugins` | **Date**: 2026-03-05  
**Applies to**: All plugin `plugin.yaml` files that declare agents.

---

## Purpose

This contract defines the canonical schema for the `agents` block in a `plugin.yaml` manifest after the 004 migration. It specifies which fields are required, their types, and validation rules enforced at startup.

---

## Schema

```yaml
# plugin.yaml — agents section schema
agents:
  <agent_name>:                  # string; unique within this plugin; forms plugin::<agent_name>
    description: string          # REQUIRED. Human-readable role summary.
    module: string               # REQUIRED. Relative path to Python file, e.g. "agents/react_agent.py".
                                 #   Must physically reside within this plugin directory (FR-006).
    entry_fn: string             # REQUIRED. Callable name that returns a pocketflow.Flow instance.
    llm_profile: string          # OPTIONAL. Named profile key from pocketcode.yml → llm.profiles.
                                 #   If omitted, runtime uses the global default profile.
    tools:                       # OPTIONAL. List of tool names this agent may invoke.
      - <tool_name>              #   Bare names resolved local-first, then core namespace.
                                 #   Cross-plugin: "core::read_file" form is accepted.
    handoff_agents:              # OPTIONAL. Agents this agent may hand off control to.
      - <plugin::agent>          #   MUST be fully-qualified "plugin::agent" form after 004.
                                 #   Bare short names are forbidden (FR-007).
    prompts:                     # OPTIONAL. Paths to prompt markdown files, relative to plugin dir.
      - string
```

---

## Validation Rules (enforced at startup)

| Rule | Error behaviour |
|------|----------------|
| `module` path must exist inside the plugin directory | *startup error*: "Module file not found: {path}" |
| `entry_fn` must be callable and return a `pocketflow.Flow` | *startup error*: "entry_fn '{fn}' did not return a Flow" |
| Each `handoff_agents` entry must resolve to a registered agent | *startup error*: "Agent '{ref}' not found. Did you mean '{suggestion}'? Enable the '{plugin}' plugin to use it." |
| Bare short name in `handoff_agents` that matches agents in >1 loaded plugin | *startup/validation error*: "Ambiguous handoff target '{name}': matched by [{plugin_a}, {plugin_b}]. Use fully-qualified form." |
| Same agent short name registered by >1 loaded plugin | *startup/validation error*: "Duplicate agent short name '{name}' registered by [{plugin_a}, {plugin_b}]." |
| `module` cross-plugin reference (path outside plugin dir) | *startup error*: "Cross-plugin module references are not permitted (FR-006)." |

---

## Reference Manifests (post-migration)

### `core/plugin.yaml` — agents section

```yaml
agents:
  react:
    description: >
      General-purpose ReAct agent. Reasons, calls core tools, and observes
      results in a Reason → Act → Observe loop until a final answer is reached.
    module: agents/react_agent.py
    entry_fn: create_flow
    llm_profile: gemini_default
    tools:
      - read_file
      - write_to_file
      - list_files
      - create_directory
      - glob_files
      - search_code
      - execute_command
      - ask_user_input
      - confirm_user_input
      - git_status
      - git_diff
      - git_add
      - git_commit
      - git_pull
      - git_push
```

### `coder/plugin.yaml` — agents section

```yaml
agents:
  coder:
    description: Code implementation and editing specialist.
    module: agents/coder_agent.py
    entry_fn: create_flow
    llm_profile: gemini_default
    tools:
      - write_to_file        # local
      - create_directory     # local
      - git_diff             # local
      - core::read_file
      - core::list_files
      - core::glob_files
      - core::search_code
      - core::execute_command
      - core::git_status
      - core::git_add
      - core::git_commit
      - core::git_pull
      - core::git_push
    handoff_agents:
      - architect::architect
      - asker::ask
```

### `architect/plugin.yaml` — agents section

```yaml
agents:
  architect:
    description: Architecture and planning specialist.
    module: agents/architect_agent.py
    entry_fn: create_flow
    llm_profile: gemini_default
    tools:
      - read_file            # local
      - list_files           # local
      - search_code          # local
      - core::glob_files
    handoff_agents:
      - coder::coder
      - asker::ask
```

### `asker/plugin.yaml` — agents section

```yaml
agents:
  ask:
    description: Repository Q&A and clarification specialist.
    module: agents/asker_agent.py
    entry_fn: create_flow
    llm_profile: gemini_fast
    tools:
      - ask_user             # local (AskUserInputTool)
      - core::read_file
      - core::list_files
      - core::glob_files
      - core::search_code
    handoff_agents:
      - coder::coder
      - architect::architect
```

### `micromanager/plugin.yaml` — agents section (handoff update only)

```yaml
agents:
  micromanager:
    # ... existing fields unchanged ...
    handoff_agents:
      - coder::coder
      - architect::architect
      - asker::ask
```

---

## Breaking Changes from this Migration

| Old reference | New reference | Error if stale |
|---|---|---|
| `core::coder` | `coder::coder` | startup hard-fail with suggestion |
| `core::architect` | `architect::architect` | startup hard-fail with suggestion |
| `core::ask` | `asker::ask` | startup hard-fail with suggestion |
| `core.coder` (dot form) | `coder::coder` | startup hard-fail |
| bare `architect` in handoff (if ambiguous) | `architect::architect` | startup/validation error |
