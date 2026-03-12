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
- `workspace_paths`: canonical discovery list for additional plain namespace roots outside discovered resource roots
- `storage`: runtime-managed filesystem locations for saved sessions and Textual entry history
- `require_tool_confirmation`: global default confirmation behavior seed
- `auto_approved_tools`: tools that default to `allow`
- `auto_confirm_tools`: bypass confirmation at runtime
- `tool_confirmation`: persisted confirmation policy configuration
- `llm_overrides`: config-level flow and handoff LLM overrides
- `textual`: Textual UI settings and persisted selection state

`runtime.default_agent` is normalized against the loaded flow registry during engine startup and when saved from the Textual system-settings editor. Legacy values such as `core::react` are accepted, but when the backing registry can qualify them they are persisted in canonical dotted form such as `core.react`.

### Runtime storage paths

Runtime-managed state lives outside `.pocketcode/` by default and is configured in `runtime.storage`:

```yaml
runtime:
  storage:
    session_state_dir: .pocketstate
    entry_history_dir: .pockethist
```

- `session_state_dir`: directory that stores saved-session JSON files under `sessions/`
- `entry_history_dir`: directory that stores the Textual accepted-input history file `textual_entry_history.json`

Relative paths resolve from the workspace root. Absolute paths are also accepted.

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

`tool_policies` keys accept canonical dotted ids and typed `tool:` references. The runtime normalizes them to canonical dotted tool ids before lookup and persistence.

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
- `control_presentation`
- `default_skills`
- `selection_presets`
- `last_used`

The engine still reads legacy `workspace_mode` values from older configs, but `workspace_view` is the canonical persisted key.

At Textual startup, the saved `workspace_view` restores layout details such as inspector visibility, but the shell still opens on the `chat` view by default. Changing the workspace view from inside Textual continues to switch to that preset's paired view.

`last_used` can persist:

- active profile
- global LLM override
- session confirmation default
- `auto_confirm_tools`

`control_presentation` is the canonical Textual control-layout setting. Supported values are:

- `inline`
- `modal`

`inline` renders pending runtime input controls directly in the Textual chat/run surfaces, replaces those controls with the submitted value after acceptance, and keeps debugger breakpoint controls on-screen in the Run view. `modal` opens those control flows in popup screens instead. Older configs that still contain `user_input_popups: true` are read as `control_presentation: modal`.

Session-only inspector selections are not written into `runtime.textual.last_used`. They live in the active saved session under `<runtime.storage.session_state_dir>/sessions/*.json`.

Current skill persistence order inside `runtime.textual` is:

1. active saved-session per-profile override
2. `<primary_resource_root>/<profile>.agent.yaml -> skills`
3. active saved-session global override
4. `default_skills`

`runtime.textual.selection_presets` can still store reusable snapshot data, including per-profile tool and skill selections, but applying a preset hydrates the current session state rather than creating new persistent `last_used` overrides.

When selection presets are saved, any registry-backed tool references embedded in per-profile tool selections or per-profile tool-confirmation overrides are normalized to canonical dotted ids before they are written to `pocketcode.yml`.

## Workspace Resource Layout

PocketCoder distinguishes between the workspace root and one or more discovered `resource_root` folders inside it.

The runtime auto-discovers resource roots from top-level hidden directories whose names begin with `.pocket` and that contain recognized resource collections or flat convention files such as `*.md`, `*.agent.md`, `*.agent.yaml`, `*.tool.md`, `*.prompt.md`, or `*.tool.py`. Recognized collections now include `agents/`, `prompts/`, `tools/`, `skills/`, `llm-profiles/`, and typed collection folders such as `agent.<group>/`, `tool.<group>/`, and `skill.<name>/`.

Examples:

- `.pocketcode/`
- `.pocketflow/`

Each resource root can provide this extension surface:

```text
<resource_root>/
├── <flow>.md
├── <flow>.prompt.md
├── <flow>.tool.py
├── <tool>.tool.md
├── <tool>.tool.py
├── agents/
├── prompts/
├── tools/
├── llm-profiles/
├── skills/
├── agent.<group>/
├── tool.<group>/
├── skill.<name>/
└── vm/
```

Additional collection conventions:

- `prompts/**/*.md` registers prompts using the path under `prompts/`, with `/` converted to `.`
- `tools/**/*.tool.md` and `tools/**/*.tool.py` load direct workspace tools recursively
- `agents/**/*.agent.md` and `agents/**/*.agent.yaml` load workspace agent profiles recursively
- `tool.<group>/` is an extra recursive tool root; Markdown tool wrappers default to `<group>.<relative_name>`
- `agent.<group>/` is an extra recursive agent root; Markdown agent profiles default to `<group>.<relative_name>`
- `skill.<name>/` is equivalent to `skills/<name>/` for a single skill bundle

Configured workspace discovery paths are separate from resource roots. They are declared in `runtime.workspace_paths` and are used for additional plain namespace roots such as `.github/`:

```yaml
runtime:
  workspace_paths:
    - .github
```

Rules:

- each entry is resolved relative to the workspace root unless already absolute
- when a path is a plain namespace folder, the namespace is the folder basename with any leading `.` removed
- plain namespace folders load executable `*.md`, `*.prompt.md`, and `*.tool.py`
- adjacent `tool_files` referenced from a Markdown program are resolved relative to that Markdown file before flow finalization
- built-in `core` is loaded from the package resource root at `pocketcode/.pocketcore/` and does not need an entry in `workspace_paths`

Example:

```text
.github/
├── speckit.plan.md
├── speckit.plan.prompt.md
└── speckit.plan.tool.py
```

This yields:

- flow `github.speckit.plan`
- prompt `github.speckit.plan`
- tool exports under `github.*`

Resource-root namespace-pack example:

```text
.pocketcode/
├── coder.coder.md
├── coder.system.prompt.md
├── coder.git.tool.py
├── workspace_builder.plugin_builder.md
└── workspace_builder.system.prompt.md
```

Runtime session state is stored under:

```text
<runtime.storage.session_state_dir>/sessions/
```

Preferred flat convention files:

- `<resource_root>/<flow>.md` for executable Markdown flows
- `<resource_root>/<flow>.prompt.md` for sibling prompt text auto-attached to that flow
- `<resource_root>/<flow>.tool.py` for sibling helper tools auto-attached to that flow when the flow omits `tool_files`
- `<resource_root>/<tool>.tool.md` plus `<resource_root>/<tool>.tool.py` for standalone Markdown tool assets
- legacy flat `<resource_root>/<agent>.agent.md` and `<resource_root>/<agent>.agent.yaml` workspace agent profiles that still load for compatibility
- `<resource_root>/prompts/**/*.md` for prompt collections
- `<resource_root>/tools/**/*.tool.md` and `<resource_root>/tools/**/*.tool.py` for recursive tool collections
- `<resource_root>/agents/**/*.agent.md` and `<resource_root>/agents/**/*.agent.yaml` for recursive agent collections
- `<resource_root>/tool.<group>/...` and `<resource_root>/agent.<group>/...` for typed grouped collections; new agent writes default to `agent.<group>/...`
- `<resource_root>/skill.<name>/SKILL.md` as a single-skill alias beside `skills/<name>/SKILL.md`

Additional directories still used by the runtime:

- `llm-profiles/`: workspace-backed LLM profile YAML files
- `<runtime.storage.session_state_dir>/sessions/`: runtime-managed saved session JSON files
- `<runtime.storage.entry_history_dir>/textual_entry_history.json`: Textual accepted-input history
- `skills/`: skill packs with `SKILL.md` and optional assets
- `vm/`: standalone StackVM `.vm` or Markdown `.md` scripts used by the `/stackvm` CLI commands; these are not auto-registered as flows until a direct `/stackvm run` or `/stackvm debug` invocation synthesizes a temporary VM flow for the current command

See `markdown_assets.md` for the canonical file formats and validation rules for Markdown-backed assets.

For new executable assets, use the flat convention files at the resource-root top level.

Built-in core filesystem tools are not allowed to operate outside the workspace root itself. The package-owned `core.read_file`, `core.write_to_file`, `core.create_directory`, `core.list_files`, `core.glob_files`, and staged file-edit helpers are rooted to the current workspace directory.

## Workspace LLM Profiles

Workspace LLM profiles are loaded from every discovered `<resource_root>/llm-profiles/<name>.yaml`. New or cloned profiles are written to the primary resource root.

They are loaded in addition to:

- `llm.profiles` from `pocketcode.yml`
- plugin-provided `llm_profiles`

These files are the editable workspace-backed copies used by the Textual clone/edit flows.

## Workspace Agent Profiles

Workspace agent profiles are loaded from every discovered `<resource_root>/<name>.agent.yaml`, `<resource_root>/<name>.agent.md`, `<resource_root>/agents/**/*.agent.yaml`, `<resource_root>/agents/**/*.agent.md`, and typed `agent.<group>/` collection. New or cloned profiles are written to the primary resource root using the grouped `agent.<group>/...` convention. For example, `review.safe` writes to `agent.review/safe.agent.md`, while `review` writes to `agent.review/review.agent.md`.

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

Workspace Markdown asset authoring now uses:

- `<resource_root>/<name>.md` for flow assets
- `<resource_root>/<name>.tool.md` for tool assets
- `<resource_root>/agent.<group>/...` for agent assets, with the first name segment becoming the group directory

The `/asset` command group and the Textual editor use those paths when creating, cloning, editing, and deleting workspace Markdown assets. Legacy flat agent files remain editable in place when they already exist.

Configured namespace assets are not written through `/asset`. They are loaded read-only from the roots listed in `runtime.workspace_paths`, while `.pocketcode/` and other discovered resource roots are handled by resource-root discovery.

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

- configured namespace roots and flat namespace-pack roots
- namespace-local prompts, tools, agents, and flow modules
- workspace skills, prompts, tools, and agents

### `.pocketcodeignore`

There are two relevant ignore scopes:

- direct resources and flat namespace-pack assets inside a resource root use `<resource_root>/.pocketcodeignore`
- package/external compatibility roots use workspace-root `.pocketcodeignore`

Patterns are gitignore-style and support re-includes with `!`.

## Canonical Naming Guidance

Internally, the registry stores qualified names as dotted namespaces such as `core.react`.

Registry-backed references accept canonical dotted ids and typed forms such as `tool:core.read_file`, `flow:core.react`, `agent:core.react`, and `prompt:resource_root.pocketcode.review`. When authoring new configs, prefer the canonical dotted form unless a field is explicitly typed, such as `prompt:` references in prompt bundles.
