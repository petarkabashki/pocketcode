Always update the documentation to be consistent with the codebase and reflect all changes.

Always for python load the local python environment by running `source` on .venv/bin/activate

---

## Agent System

### Concept

An **Agent** is a named configuration object that governs how a flow behaves during a session:
- Which **LLM profile** to use (overrides engine defaults at tier 4.5)
- Which **tools** are permitted (allowlist — `None` means all tools)
- Extra **system prompt files** appended to the flow's base prompt (`extra_prompts`)
- **Tool confirmation** policy defaults and per-tool overrides

Every flow automatically gets a *synthesised* default agent on startup. Workspace-local YAML files and plugin-declared blocks can override defaults.

Workspace-local customisation also lives under `.pocketcode/`:
- `.pocketcode/agents/` for workspace agent YAML files
- `.pocketcode/plugins/` for workspace plugins
- `.pocketcode/tools/` for shared tools auto-registered under the `workspace` namespace and visible to every flow whose tool scope is unrestricted
- `.pocketcode/prompts/` for shared prompt files; files are registered under the `workspace` namespace and are also valid fallback prompt sources for plugin agents and agent `extra_prompts`

### Agent Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | — | Unique agent identifier |
| `flow` | `str` | — | Qualified flow name this agent targets (`plugin::flow`) |
| `description` | `str` | `""` | Human-readable description |
| `llm_profile` | `str \| None` | `None` | LLM profile name; `None` inherits from engine |
| `extra_prompts` | `List[str]` | `[]` | File paths to append to system prompt |
| `tools` | `List[str] \| None` | `None` | Tool allowlist; `None` = unrestricted |
| `tool_confirmation` | `dict` | `{}` | Keys: `default` (policy), `overrides` (per-tool policies) |
| `source` | `str` | `"synthesised"` | One of `"synthesised"`, `"plugin"`, `"workspace"` |
| `source_path` | `Path \| None` | `None` | Path to the workspace YAML file if applicable |

### Precedence (Name Collision)

Plugin-declared > Workspace file > Synthesised default

### LLM Resolution Tier Order

1. CLI per-flow override
2. Config per-flow override
3. CLI global override
4. Dynamic per-flow override
4.5 **Active agent** `llm_profile`
5. Flow definition `llm_profile`
6. Default LLM profile
7. LLM router default

### Tool Confirmation Tier Order

**PRE-CHECK**: Tool not in `agent.tools` → deny immediately (no confirmation prompt)

1. Session `[flow][tool]`
1.5 **Agent** `tool_confirmation.overrides[tool]`
2. Config `[flow][tool]`
3. Session global `[tool]`
4. Session `[flow].default`
4.5 **Agent** `tool_confirmation.default`
5. Config `[flow].default`
6. Config global `[tool]`
7. Session global default
8. Config global default

### CLI Commands

```
/agent list                                 List all available agents.
/agent show [agent_name]                    Show details (default: active agent).
/agent switch <agent_name>                  Activate an agent.
/agent clone <source> <new_name>            Clone an agent to a new workspace file.
/agent edit llm <agent> <profile|inherit>   Set or clear the agent LLM override.
/agent edit prompts <agent> <paths...>      Replace extra prompt paths.
/agent edit prompts <agent> clear           Clear extra prompt paths.
/agent help                                 Show help.

/flow <flow_name> [--agent <agent_name>]    Set flow + optionally activate an agent.
```

Compatibility alias: `/agent-profile` → `/agent`

### Status Bar Format

```
Runtime flow: <runtime> | Flow: <flow> | Agent: <agent> | LLM: <llm_profile> (<model>)
```

### Workspace Agent YAML Schema

Stored in `.pocketcode/agents/<name>.yaml`:

```yaml
name: my-agent          # required
flow: plugin::flowname  # required (qualified name)
description: "Optional description"
llm_profile: gpt-4o     # optional; omit to inherit
tools:                  # optional; omit for unrestricted
  - filesystem::read_file
  - search::web_search
extra_prompts:          # optional file paths
  - prompts/safety.md   # relative to this file or .pocketcode/
tool_confirmation:
  default: confirm      # optional: allow | confirm | deny
  overrides:
    filesystem::delete_file: deny
```

### Plugin plugin.yaml Inline Block

```yaml
flows:
  myflow:
    # ... existing flow fields ...
    default_agent:
      name: myplugin::myflow:safe
      description: "Safe mode agent"
      llm_profile: gpt-4o-mini
      tools:
        - search::web_search
      tool_confirmation:
        default: confirm
```

### Key Files

| File | Purpose |
|------|---------|
| `pocketcode/core/agent_manager.py` | Agent registry exports |
| `pocketcode/core/agent_profile_manager.py` | Agent registry implementation: load, get, list, clone, save |
| `pocketcode/core/runtime_models.py` | `Agent` and `FlowDefinition` dataclasses |
| `pocketcode/core/engine.py` | `set_flow()`, `set_active_agent()`, `list_flows()`, `list_available_agents()` |
| `pocketcode/core/agent_runtime.py` | LLM tier 4.5, tool filtering, extra_prompts injection |
| `pocketcode/core/tool_runtime.py` | Confirmation tiers 1.5/4.5, tool allowlist pre-check |
| `pocketcode/cli/command_handler.py` | `/flow` and `/agent` CLI surface, plus `/agent-profile` compatibility alias |
| `pocketcode/cli/completers.py` | `AgentCompleter` for tab-completion |
| `pocketcode/cli/textual_app.py` | Status bar Flow/Agent segments, suggestion list |
| `tests/unit/test_agent_profile_manager.py` | Agent manager unit tests |
| `tests/unit/test_agent_profile_resolution.py` | LLM/confirmation/allowlist unit tests |
