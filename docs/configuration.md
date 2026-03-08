# Configuration

This document describes the current workspace configuration model.

## Required Root Config

PocketCoder requires a workspace-root `pocketcode.yml`.

`pocketcode.config.loader.resolve_settings_path()` only resolves configuration from:

- `<workspace>/pocketcode.yml`

If that file is missing, startup fails.

## Environment Variable Resolution

`load_settings()` performs recursive `${VAR_NAME}` expansion across the loaded YAML.

- Resolved values are substituted before runtime initialization.
- Unresolved placeholders cause startup failure.
- `llm.providers` and `llm.profiles` must both be mappings.

## Top-Level Sections

Current expected sections are:

- `llm`
- `runtime`

Additional sections may exist, but these two are the runtime-critical ones.

## `llm` Section

### Providers

`llm.providers` maps provider names to either:

- a plain API key string
- a mapping with provider-specific settings

Current provider families in the codebase:

- `gemini`
- OpenAI-compatible providers such as `openai`, `openrouter`, `xai`, and `requesty`

### Profiles

`llm.profiles` defines named model configurations.

Each profile is a mapping such as:

```yaml
llm:
  profiles:
    fast-review:
      provider: gemini
      model: gemini-3.1-flash-lite-preview
      parameters:
        temperature: 0.2
        max_output_tokens: 4096
```

`llm.default_profile` sets the default router profile when no higher-precedence override applies.

## `runtime` Section

Common runtime keys used by the current engine include:

- `default_agent`: default flow to start from
- `plugin_paths`: additional plugin roots, commonly `.pocketcode/plugins`
- `require_tool_confirmation`: global default confirmation behavior seed
- `auto_approved_tools`: tools that default to `allow`
- `auto_confirm_tools`: bypass confirmation at runtime
- `tool_confirmation`: persisted confirmation policy configuration
- `llm_overrides`: config-level flow and handoff LLM overrides
- `textual`: Textual UI settings and persisted selection state

Saved session history is not configured inside `pocketcode.yml`. It is runtime state stored separately under `.pocketcode/state/sessions/`.

### Tool confirmation config shape

Current normalized config shape is:

```yaml
runtime:
  tool_confirmation:
    default_policy: confirm
    tool_policies: {}
    agent_policies: {}
```

Where `agent_policies` is keyed by flow name and can contain:

- `default_policy`
- `tool_policies`

Supported policies are:

- `allow`
- `confirm`
- `deny`

### Textual settings

The `runtime.textual` section stores both defaults and last-used runtime state.

Common keys include:

- `theme_name`
- `workspace_mode`
- `default_skills`
- `selection_presets`
- `last_used`

`last_used` can persist:

- active profile
- active mode
- global LLM override
- enabled skills
- session confirmation default
- `auto_confirm_tools`
- per-profile tool allowlists
- per-profile tool confirmation overrides

## Workspace Resource Layout

The current workspace extension surface lives under `.pocketcode/`:

```text
.pocketcode/
├── agents/
├── llm-profiles/
├── modes/
├── plugins/
├── prompts/
├── state/
│   └── sessions/
├── skills/
└── tools/
```

Purpose of each directory:

- `agents/`: workspace-backed agent profiles in YAML
- `llm-profiles/`: workspace-backed LLM profile YAML files
- `modes/`: Markdown-authored runtime overlays
- `plugins/`: workspace plugin roots discovered through `runtime.plugin_paths`
- `prompts/`: shared workspace prompt files
- `state/sessions/`: runtime-managed saved session JSON files
- `skills/`: skill packs with `SKILL.md` and optional assets
- `tools/`: shared workspace Python tools auto-registered under `workspace`

## Workspace LLM Profiles

Workspace LLM profiles are stored at `.pocketcode/llm-profiles/<name>.yaml`.

They are loaded in addition to:

- `llm.profiles` from `pocketcode.yml`
- plugin-provided `llm_profiles`

These files are the editable workspace-backed copies used by the Textual clone/edit flows.

## Workspace Agent Profiles

Workspace agent profiles live at `.pocketcode/agents/<name>.yaml`.

Current schema:

```yaml
name: my-review-profile
flow: core.react
description: Restrictive review profile
llm_profile: fast-review
tools:
  - core.read_file
  - core.search_code
extra_prompts:
  - prompts/review.md
tool_confirmation:
  default: confirm
  overrides:
    core.execute_command: deny
```

Notes:

- `flow` is required.
- `tools` is optional. When omitted, the profile inherits the flow tool set.
- `extra_prompts` are resolved relative to the profile file first, then against plugin and workspace fallback roots.

## Prompt Loading

Prompt bundles are loaded through `pocketcode.core.prompt_loader`.

Supported features:

- inline prompt fields
- prompt file references
- prompt file lists
- `{{ include:path.md }}` expansion
- cycle detection for nested includes
- fallback resolution through workspace prompt roots

Flow prompt sources are stored on each `FlowDefinition.prompt_sources`.

## Discovery Controls

The runtime supports two non-destructive ways to disable resources.

### `.disabled` path components

If any path component contains `.disabled`, that resource tree is skipped.

This applies to:

- plugin roots
- plugin-local prompts, tools, agents, and flow modules
- workspace modes, skills, prompts, tools, and agents

### `.pocketcodeignore`

There are two relevant ignore scopes:

- workspace-owned `.pocketcode/` resources use `.pocketcode/.pocketcodeignore`
- package/external plugin roots use workspace-root `.pocketcodeignore`

Patterns are gitignore-style and support re-includes with `!`.

## Canonical Naming Guidance

Internally, the registry stores qualified names as `plugin.resource`.

The configuration surface may still use `plugin::resource` in places, and the runtime normalizes it. When authoring new configs, prefer the canonical `plugin.resource` form unless you are editing an existing file that already uses `::` consistently.