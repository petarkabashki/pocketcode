# Configuration

This document describes the current workspace configuration model.

## Required Root Config

PocketCoder requires a workspace-root `pocketcode.yml`.

`pocketcode.config.loader.resolve_settings_path()` only resolves configuration from:

- `<workspace>/pocketcode.yml`

If that file is missing, startup fails.

The same workspace root also acts as the default filesystem safety boundary for built-in file and directory tools during runtime. Paths that resolve outside the startup working directory are rejected.

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
- `plugin_paths`: additional plugin roots; discovered resource-root plugin folders such as `.pocketcode/plugins` and `.pocketflow/plugins` are also scanned automatically
- `require_tool_confirmation`: global default confirmation behavior seed
- `auto_approved_tools`: tools that default to `allow`
- `auto_confirm_tools`: bypass confirmation at runtime
- `tool_confirmation`: persisted confirmation policy configuration
- `llm_overrides`: config-level flow and handoff LLM overrides
- `textual`: Textual UI settings and persisted selection state

`runtime.default_agent` is normalized against the loaded flow registry during engine startup and when saved from the Textual system-settings editor. Legacy values such as `core::react` are accepted, but when the backing registry can qualify them they are persisted in canonical `plugin.resource` form such as `core.react`.

Saved session history is not configured inside `pocketcode.yml`. It is runtime state stored separately under `<primary_resource_root>/state/sessions/`.

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

`tool_policies` keys accept canonical `plugin.resource`, legacy `plugin::resource`, and typed `tool:` references. The runtime normalizes them to canonical dotted tool ids before lookup and persistence.

Session confirmation overrides follow the same rule when they are written into saved-session state: tool and agent keys are canonicalized to dotted registry ids, while invalid or unresolvable policy entries are dropped.

Supported policies are:

- `allow`
- `confirm`
- `deny`

### Textual settings

The `runtime.textual` section stores both defaults and last-used runtime state.

Common keys include:

- `theme_name`
- `workspace_view`
- `default_skills`
- `selection_presets`
- `last_used`

The engine still reads legacy `workspace_mode` values from older configs, but `workspace_view` is the canonical persisted key.

`last_used` can persist:

- active profile
- active mode
- global LLM override
- session confirmation default
- `auto_confirm_tools`

Session-only inspector selections are not written into `runtime.textual.last_used`. They live in the active saved session under `<primary_resource_root>/state/sessions/*.json`.

Current skill persistence order inside `runtime.textual` is:

1. active saved-session per-profile override
2. `<primary_resource_root>/agents/<profile>.yaml -> skills`
3. active saved-session global override
4. `default_skills`

`runtime.textual.selection_presets` can still store reusable snapshot data, including per-profile tool and skill selections, but applying a preset hydrates the current session state rather than creating new persistent `last_used` overrides.

When selection presets are saved, any registry-backed tool references embedded in per-profile tool selections or per-profile tool-confirmation overrides are normalized to canonical dotted ids before they are written to `pocketcode.yml`.

## Workspace Resource Layout

PocketCoder distinguishes between the workspace root and one or more discovered `resource_root` folders inside it.

The runtime auto-discovers resource roots from top-level hidden directories whose names begin with `.pocket` and that contain recognized resource collections.

Examples:

- `.pocketcode/`
- `.pocketflow/`

Each resource root can provide this extension surface:

```text
<resource_root>/
├── agents/
├── flows/
├── llm-profiles/
├── modes/
├── plugins/
├── prompts/
├── skills/
└── tools/
```

Runtime session state is stored under:

```text
<primary_resource_root>/state/sessions/
```

Purpose of each directory:

- `agents/`: workspace-backed agent profiles in YAML or Markdown
- `flows/`: workspace-backed Markdown flow definitions
- `llm-profiles/`: workspace-backed LLM profile YAML files
- `modes/`: Markdown-authored runtime overlays
- `plugins/`: nested plugin roots under this resource root
- `prompts/`: shared direct prompt resources for this resource root
- `state/sessions/`: runtime-managed saved session JSON files under the primary resource root
- `skills/`: skill packs with `SKILL.md` and optional assets
- `tools/`: shared direct Python or Markdown-backed tools auto-registered under `resource_root.<name>`; the default `.pocketcode/` root is also aliased under `workspace`

See `markdown_assets.md` for the canonical file formats and validation rules for Markdown-backed assets.

Built-in core filesystem tools are not allowed to operate outside the workspace root itself. Direct tools under `<resource_root>/tools/` can implement their own path rules, but the package-owned `core.read_file`, `core.write_to_file`, `core.create_directory`, `core.list_files`, `core.glob_files`, and staged file-edit helpers are rooted to the current workspace directory.

## Workspace LLM Profiles

Workspace LLM profiles are loaded from every discovered `<resource_root>/llm-profiles/<name>.yaml`. New or cloned profiles are written to the primary resource root.

They are loaded in addition to:

- `llm.profiles` from `pocketcode.yml`
- plugin-provided `llm_profiles`

These files are the editable workspace-backed copies used by the Textual clone/edit flows.

## Workspace Agent Profiles

Workspace agent profiles are loaded from every discovered `<resource_root>/agents/<name>.yaml` and `<resource_root>/agents/<name>.md`. New or cloned profiles are written to the primary resource root.

Current YAML schema:

```yaml
name: my-review-profile
flow: core.react
description: Restrictive review profile
llm_profile: fast-review
skills:
  - python-testing
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
- `skills` is optional. When omitted, the profile falls back to the global Textual skill selection order.
- `tools` is optional. When omitted, the profile inherits the flow tool set.
- `extra_prompts` are resolved relative to the profile file first, then against plugin and workspace fallback roots.
- workspace Markdown-backed profiles use the same front matter fields and store their inline guidance in the Markdown body.
- `{{ include:... }}` and `{{ import:prompt:... }}` directives inside Markdown-backed agent bodies are expanded during load.
- saving a workspace agent profile rewrites registry-backed `flow`, `tools`, and `tool_confirmation.overrides` entries to canonical dotted ids; `prompt:` entries remain typed and file-path prompt entries remain unchanged.
- saving a Markdown-backed workspace agent profile preserves Markdown format rather than converting it to YAML.

Workspace Markdown asset authoring also uses:

- `<resource_root>/flows/<name>.md` for workspace flow assets
- `<resource_root>/tools/<name>.md` for workspace tool assets

The `/asset` command group and the Textual editor use those locations when creating, cloning, editing, and deleting workspace Markdown assets.

## Prompt Loading

Prompt bundles are loaded through `pocketcode.core.prompt_loader`.

Supported features:

- inline prompt fields
- prompt file references
- prompt resource references such as `prompt:resource_root.pocketcode.review`
- prompt file lists
- `{{ include:path.md }}` expansion
- `{{ import:prompt:resource_root.pocketcode.review }}` expansion
- cycle detection for nested includes
- fallback resolution through workspace prompt roots
- resource-root-relative paths such as `prompts/review.md` when prompt fallback directories are in use

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

- direct resources and nested plugins inside a resource root use `<resource_root>/.pocketcodeignore`
- package/external plugin roots use workspace-root `.pocketcodeignore`

Patterns are gitignore-style and support re-includes with `!`.

## Canonical Naming Guidance

Internally, the registry stores qualified names as `plugin.resource`.

The configuration surface may still use `plugin::resource` in places, and the runtime normalizes it. Registry-backed references also accept typed forms such as `tool:core.read_file`, `flow:core.react`, `agent:core.react`, and `prompt:resource_root.pocketcode.review`. When authoring new configs, prefer the canonical `plugin.resource` form unless a field is explicitly typed, such as `prompt:` references in prompt bundles.
