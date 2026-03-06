Always update the documentation to be consistent with the codebase and reflect all changes.

Always for python load the local python environment by running `source` on .venv/bin/activate

---

## Agent Profile System

### Concept

An **AgentProfile** is a named configuration object that governs how an agent behaves during a session:
- Which **LLM profile** to use (overrides engine defaults at tier 4.5)
- Which **tools** are permitted (allowlist — `None` means all tools)
- Extra **system prompt files** appended to the agent's base prompt (`extra_prompts`)
- **Tool confirmation** policy defaults and per-tool overrides

Every agent automatically gets a *synthesised* default profile on startup. Workspace-local YAML files and plugin-declared blocks can override defaults.

### AgentProfile Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | — | Unique profile identifier |
| `agent` | `str` | — | Qualified agent name this profile targets (`plugin::agent`) |
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

1. CLI per-agent override
2. Config per-agent override
3. CLI global override
4. Dynamic per-agent override
4.5 **Active agent profile** `llm_profile`
5. Agent definition `llm_profile`
6. Default LLM profile
7. LLM router default

### Tool Confirmation Tier Order

**PRE-CHECK**: Tool not in `profile.tools` → deny immediately (no confirmation prompt)

1. Session `[agent][tool]`
1.5 **Profile** `tool_confirmation.overrides[tool]`
2. Config `[agent][tool]`
3. Session global `[tool]`
4. Session `[agent].default`
4.5 **Profile** `tool_confirmation.default`
5. Config `[agent].default`
6. Config global `[tool]`
7. Session global default
8. Config global default

### CLI Commands

```
/agent-profile list                         List all available agent profiles.
/agent-profile show [profile_name]          Show details (default: active profile).
/agent-profile switch <profile_name>        Activate an agent profile.
/agent-profile clone <source> <new_name>    Clone a profile to a new workspace file.
/agent-profile help                         Show help.

/agent <agent_name> [--agent-profile <profile_name>]   Set agent + optionally activate a profile.
```

Short alias: `/ap` → `/agent-profile`

### Status Bar Format

```
Runtime flow: <flow> | Agent: <agent> | Profile: <profile> | LLM: <llm_profile> (<model>)
```

### Workspace Profile YAML Schema

Stored in `.pocketcode/agent-profiles/<name>.yaml`:

```yaml
name: my-profile          # required
agent: plugin::agentname  # required (qualified name)
description: "Optional description"
llm_profile: gpt-4o       # optional; omit to inherit
tools:                    # optional; omit for unrestricted
  - filesystem::read_file
  - search::web_search
extra_prompts:            # optional file paths
  - prompts/safety.md     # relative to this file or .pocketcode/
tool_confirmation:
  default: confirm        # optional: allow | confirm | deny
  overrides:
    filesystem::delete_file: deny
```

### Plugin plugin.yaml Inline Block

```yaml
agents:
  myagent:
    # ... existing agent fields ...
    default_agent_profile:
      name: myplugin::myagent:safe   # optional; defaults to qualified agent name
      description: "Safe mode profile"
      llm_profile: gpt-4o-mini
      tools:
        - search::web_search
      tool_confirmation:
        default: confirm
```

### Key Files

| File | Purpose |
|------|---------|
| `pocketcode/core/agent_profile_manager.py` | Profile registry: load, get, list, clone, save |
| `pocketcode/core/runtime_models.py` | `AgentProfile` and `AgentDefinition` dataclasses |
| `pocketcode/core/engine.py` | `active_agent_profile`, `set_active_agent_profile()`, `list_agent_profiles()` |
| `pocketcode/core/agent_runtime.py` | LLM tier 4.5, tool filtering, extra_prompts injection |
| `pocketcode/core/tool_runtime.py` | Confirmation tiers 1.5/4.5, tool allowlist pre-check |
| `pocketcode/cli/command_handler.py` | `/agent-profile` CLI surface, `--agent-profile` flag |
| `pocketcode/cli/completers.py` | `AgentProfileCompleter` for tab-completion |
| `pocketcode/cli/textual_app.py` | Status bar Profile segment, suggestion list |
| `tests/unit/test_agent_profile_manager.py` | Manager unit tests |
| `tests/unit/test_agent_profile_resolution.py` | LLM/confirmation/allowlist unit tests |
