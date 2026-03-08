# Agent System

This document is the canonical reference for PocketCoder's current agent-profile system.

Use this document together with:

- `architecture.md` for runtime loading and precedence behavior
- `configuration.md` for workspace file locations and configuration
- `cli.md` for the command surface
- `pocketflow_agents.md` for the relationship between flows, agent profiles, modes, and skills

## Concept

An agent profile is a named configuration object that governs how a flow behaves during a session.

An agent profile can control:

- which LLM profile to use
- which tools are permitted
- which extra prompt files are appended to the flow prompt
- which default and per-tool confirmation policies apply

Every flow gets a synthesised default profile at load time. Plugin-declared profiles and workspace profiles can override that default.

## Agent Profile Fields

The runtime model is `CompositeAgent` in `pocketcode/core/runtime_models.py`.

Current fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | none | Unique profile identifier |
| `flow` | `str` | none | Qualified target flow name |
| `description` | `str` | `""` | Human-readable description |
| `llm_profile` | `str \| None` | `None` | LLM profile override |
| `inline_prompt` | `str` | `""` | Inline prompt text appended after the flow prompt |
| `extra_prompts` | `List[str]` | `[]` | Additional prompt file references |
| `skills` | `List[str] \| None` | `None` | Default enabled skills; `None` means use global skill defaults |
| `tools` | `List[str] \| None` | `None` | Tool allowlist; `None` means inherit flow tool surface |
| `tool_confirmation` | `dict` | `{}` | Confirmation defaults and per-tool overrides |
| `source` | `str` | `"synthesised"` | One of `synthesised`, `plugin`, or `workspace` |
| `source_path` | `Path \| None` | `None` | Source YAML path for workspace-backed profiles |

## Source And Precedence

Agent profiles are loaded through `AgentManager` with this effective precedence:

1. plugin-declared inline `default_agent`
2. plugin-local `agents/*.yaml`
3. workspace `.pocketcode/agents/*.yaml`
4. synthesised defaults built from flow definitions

On name collision, the higher-precedence source wins.

## LLM Resolution Tier Order

Current resolution order for an active turn is:

1. CLI per-flow override
2. config per-flow override
3. CLI global override
4. dynamic runtime override
5. active agent profile `llm_profile`
6. flow definition `llm_profile`
7. default LLM profile
8. router default

## Tool Confirmation Tier Order

Before confirmation is evaluated, the runtime denies any tool outside the active allowlist.

Current confirmation resolution order is:

1. session per-flow per-tool override
2. active profile per-tool override
3. config per-flow per-tool override
4. session global per-tool override
5. session per-flow default
6. active profile default
7. config per-flow default
8. config global per-tool override
9. session global default
10. config global default

## Workspace File Locations

The agent-profile system uses these workspace paths:

- `.pocketcode/agents/` for workspace profile YAML files
- `.pocketcode/llm-profiles/` for workspace LLM profile YAML files
- `.pocketcode/plugins/` for workspace plugins
- `.pocketcode/tools/` for shared workspace tools under the `workspace` namespace
- `.pocketcode/prompts/` for shared workspace prompts and prompt fallback resolution

## Workspace LLM Profile Schema

Workspace LLM profiles are stored in `.pocketcode/llm-profiles/<name>.yaml`.

Example:

```yaml
name: my-fast-clone
provider: gemini
model: gemini-2.5-flash
parameters:
  temperature: 0.2
  max_output_tokens: 3072
```

## Workspace Agent Profile Schema

Workspace agent profiles are stored in `.pocketcode/agents/<name>.yaml`.

Example:

```yaml
name: my-agent
flow: core.react
description: Optional description
llm_profile: fast-review
skills:
  - python-testing
tools:
  - core.read_file
  - core.search_code
extra_prompts:
  - prompts/safety.md
tool_confirmation:
  default: confirm
  overrides:
    core.execute_command: deny
```

Notes:

- `flow` is required.
- `skills` omitted means fall back to the global Textual skill selection order.
- `tools` omitted means inherit the target flow tool surface.
- `extra_prompts` are resolved relative to the profile file first, then through plugin and workspace fallback roots.

## Inline Flow Default Agent Block

Flows can define an inline default profile in `plugin.yaml`.

Example:

```yaml
flows:
  myflow:
    module: flows/myflow.py
    entry_fn: create_flow
    default_agent:
      name: myflow-safe
      description: Safe mode agent
      llm_profile: fast-review
      skills:
        - python-testing
      tools:
        - core.read_file
      tool_confirmation:
        default: confirm
```

## CLI Surface

The current agent-profile command surface is:

```text
/agent list
/agent show [agent_name]
/agent switch <agent_name>
/agent clone <source> <new_name>
/agent edit llm <agent> <profile|inherit>
/agent edit prompts <agent> <paths...>
/agent edit prompts <agent> clear
/agent tools <agent> all
/agent tools <agent> none
/agent tools <agent> set <tools...>
/agent policy default <agent> <allow|confirm|deny|reset>
/agent policy tool <agent> <tool> <allow|confirm|deny|reset>
/agent help
```

Behavior notes:

- `/agent list` shows named profiles and excludes synthesised flow defaults.
- `/agent show` defaults to the active profile when no name is supplied.
- profile editing commands apply only to workspace-backed profiles; plugin and synthesised profiles must be cloned first.

Agent command shortcuts:

- `/ag` -> `/agent`
- `/ap` -> `/agent`

Flow selection can optionally activate a profile:

```text
/flow <flow_name|auto> [--agent <agent_name>]
```

## Textual UI Notes

Current Textual agent-system controls include:

- `F3` opens the editor picker for agent config, mode config, LLM config, tool selection, and tool policies
- `F4` opens the clone picker for agent, mode, and LLM configs
- `F6` opens the Control Center for active profile selection, mode selection, LLM override, skills, tool selection, tool policy editing, selection presets, session confirmation, and system settings
- the inspector exposes inline `Skills` and `Allowed Tools` selection lists, each with a `Save` button that writes the current selection into the active workspace agent YAML
- tool entries are grouped hierarchically and can be toggled at either the group or leaf level
- searchable selection popups support `Ctrl+Down`, `Ctrl+Up`, and `Space`
- tool groups are derived from the tool source path under `tools/`
- last-used mode, profile, LLM, skill, tool, and tool-policy choices are persisted
- active-profile skill selections are persisted under `runtime.textual.last_used.agent_profiles.<profile>.skills`
- saving inspector skills writes `skills` in `.pocketcode/agents/<profile>.yaml` and then clears a matching per-profile Textual skill override
- saving inspector tools writes `tools` in `.pocketcode/agents/<profile>.yaml` and then clears a matching per-profile Textual tool override
- `Reset` clears the last-used override and `Save as Default` writes the current selection into config
- editing a plugin or synthesised profile from the Textual UI requires cloning it to a workspace-backed profile first

Current skill fallback order is:

1. active profile skill override
2. active profile YAML `skills`
3. global Textual last-used skills
4. global Textual default skills

## Status Display

The current Textual status display can appear as either separate header chips or a combined summary line.

Current display strings include:

```text
Runtime flow: <runtime_flow> | Agent: <agent> | LLM: <llm_profile> (<model>)
Agent: <agent> | LLM: <llm_profile> (<model>)
```

The UI also renders separate header labels for:

- `Runtime flow: <runtime_flow>`
- `Agent: <agent>`
- `LLM: <llm_profile> (<model>)`

## Key Files

Core implementation files:

| File | Purpose |
|------|---------|
| `pocketcode/core/agent_manager.py` | Agent registry exports |
| `pocketcode/core/agent_profile_manager.py` | Agent registry implementation |
| `pocketcode/core/runtime_models.py` | `CompositeAgent` and `FlowDefinition` dataclasses |
| `pocketcode/core/engine.py` | active flow/profile selection and persistence |
| `pocketcode/core/agent_runtime.py` | LLM resolution, tool filtering, prompt overlay logic |
| `pocketcode/core/tool_runtime.py` | confirmation policy resolution and allowlist enforcement |
| `pocketcode/cli/command_handler.py` | `/flow` and `/agent` CLI surface |
| `pocketcode/cli/completers.py` | profile completion support |
| `pocketcode/cli/textual_app.py` | Stable Textual UI import surface and re-exports |
| `pocketcode/cli/textual_ui/` | Textual status bar, control surfaces, modal screens, and UI workflows |
| `tests/unit/test_agent_profile_manager.py` | manager unit tests |
| `tests/unit/test_agent_profile_resolution.py` | precedence and resolution tests |
