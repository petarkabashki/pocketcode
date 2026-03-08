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
| `flow` | `str` | none | Qualified target flow name; accepts canonical `plugin.resource`, legacy `plugin::resource`, and typed `flow:` or `agent:` forms |
| `description` | `str` | `""` | Human-readable description |
| `llm_profile` | `str \| None` | `None` | LLM profile override |
| `inline_prompt` | `str` | `""` | Inline prompt text appended after the flow prompt |
| `extra_prompts` | `List[str]` | `[]` | Additional prompt references; each entry may be a file path or a `prompt:` resource reference |
| `skills` | `List[str] \| None` | `None` | Default enabled skills; `None` means use global skill defaults |
| `tools` | `List[str] \| None` | `None` | Tool allowlist; `None` means inherit flow tool surface |
| `tool_confirmation` | `dict` | `{}` | Confirmation defaults and per-tool overrides |
| `source` | `str` | `"synthesised"` | One of `synthesised`, `plugin`, or `workspace` |
| `source_path` | `Path \| None` | `None` | Source YAML path for workspace-backed profiles |

- `tools` entries resolve through the shared registry, so they accept `plugin.resource`, `plugin::resource`, and typed `tool:` references.

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

- `<resource_root>/agents/` for workspace profile YAML files
- `<resource_root>/llm-profiles/` for workspace LLM profile YAML files
- `<resource_root>/plugins/` for nested plugins
- `<resource_root>/tools/` for shared direct tools under `resource_root.<name>`; the default `.pocketcode/` root is also aliased under `workspace`
- `<resource_root>/prompts/` for shared direct prompts and prompt fallback resolution

Built-in core tools are package resources under `pocketcode/plugins/core/tools/`. The older `pocketcode/tools/` package remains available only as a backward-compatible import facade.

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

Workspace agent profiles are loaded from all discovered `<resource_root>/agents/<name>.yaml` locations and are saved into the primary resource root.

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
- agent-facing runtime controls such as flow selection, tool listing, and per-agent LLM overrides normalize `plugin::resource` and typed `flow:` or `agent:` references before registry lookup.
- `extra_prompts` entries beginning with `prompt:` resolve through the prompt registry.
- path-based `extra_prompts` are resolved relative to the profile file first, then through plugin and resource-root fallback roots.
- workspace-backed agent profile YAML now validates and normalizes typed refs while loading; malformed `flow`, `tools`, or `extra_prompts` entries cause that profile file to be skipped with a warning instead of failing later during runtime resolution.
- when a workspace-backed agent profile is saved or updated, registry-backed `flow`, `tools`, and `tool_confirmation.overrides` entries are written back in canonical `plugin.resource` form, while `prompt:` sources remain typed and plain path-based prompt entries remain plain paths.
- after the engine has loaded flows, tools, and prompts, agent profiles are validated again against the live registries; resolvable tool refs are canonicalized, invalid prompt-resource refs are removed with a warning, and profiles whose target flow is no longer available are dropped from the loaded registry.

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
- inline inspector tool and skill selections are session-scoped effective runtime overrides, not persistent `pocketcode.yml` state
- new sessions seed those runtime overrides from the active agent profile YAML before any session-specific changes are applied
- tool entries are grouped hierarchically and can be toggled at either the group or leaf level
- searchable selection popups support `Ctrl+Down`, `Ctrl+Up`, and `Space`
- tool groups are derived from the tool source path under `tools/`
- last-used mode, profile, and LLM choices are still persisted for Textual startup convenience
- saving inspector skills writes `skills` in `.pocketcode/agents/<profile>.yaml` and clears any matching legacy Textual override state
- saving inspector tools writes `tools` in `.pocketcode/agents/<profile>.yaml` and clears any matching legacy Textual override state
- `Reset` clears the current session override and `Save as Default` writes the current selection into config
- editing a plugin or synthesised profile from the Textual UI requires cloning it to a workspace-backed profile first

Current skill fallback order is:

1. active session per-profile skill override
2. active profile YAML `skills`
3. active session global skill override
4. Textual `default_skills`

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
