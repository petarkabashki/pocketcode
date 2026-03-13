# Agent System

This document is the canonical reference for PocketCoder's current agent system.

Use this document together with:

- `architecture.md` for runtime loading and precedence behavior
- `configuration.md` for workspace file locations and configuration
- `markdown_assets.md` for Markdown-backed agent syntax, includes, and validation
- `cli.md` for the command surface
- `pocketflow_agents.md` for the relationship between executable flows, inheritable agents, and skills

## Concept

An agent is a named configuration object that governs how a flow behaves during a session.

An authored agent can control:

- which LLM profile to use
- which reusable hooks are mixed into runtime lifecycle phases
- which tools are permitted
- which extra prompt files are appended to the flow prompt
- which default and per-tool confirmation policies apply

Every flow gets a synthesised default agent at load time. Workspace-authored agents can extend that default or any other agent.

## Agent Fields

The runtime model is `CompositeAgent` in `pocketcode/core/runtime_models.py`.

Current fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | none | Unique profile identifier |
| `flow` | `str` | none | Qualified target flow name; accepts canonical dotted ids and typed `flow:` or `agent:` forms |
| `base_agent` | `str \| None` | `None` | Optional parent agent/profile name to inherit from; Markdown and YAML also accept `extends` |
| `description` | `str` | `""` | Human-readable description |
| `llm_profile` | `str \| None` | `None` | LLM profile override |
| `inline_prompt` | `str` | `""` | Inline prompt text appended after the flow prompt |
| `extra_prompts` | `List[str]` | `[]` | Additional prompt references; each entry may be a file path or a `prompt:` resource reference |
| `hooks` | `List[str] \| None` | `None` | Ordered hook refs mixed into the agent lifecycle; `None` means inherit |
| `skills` | `List[str] \| None` | `None` | Default enabled skills; `None` means use global skill defaults |
| `tools` | `List[str] \| None` | `None` | Tool allowlist; `None` means inherit flow tool surface |
| `tool_confirmation` | `dict` | `{}` | Confirmation defaults and per-tool overrides |
| `source` | `str` | `"synthesised"` | One of `synthesised`, `namespace`, or `workspace` |
| `source_path` | `Path \| None` | `None` | Source file path for workspace-backed agents |

- `tools` entries resolve through the shared registry, so they accept canonical dotted ids and typed `tool:` references.
- `hooks` entries resolve through the shared registry, so they accept canonical dotted ids and typed `hook:` references.

## Source And Precedence

Agents are loaded through `AgentManager` with this effective precedence:

1. workspace agent profiles from discovered resource roots, with new writes defaulting to grouped `agent.<group>/` paths while legacy flat `<resource_root>/*.agent.*` files still load
2. synthesised defaults built from flow definitions

On name collision, the higher-precedence source wins.

Configured workspace namespace assets from `runtime.workspace_paths` are not part of this authored-agent search path. Their executable Markdown files register flows in `WorkspaceCatalog`; `AgentManager` then synthesizes default agents for those flows unless another agent overrides them. Matching `.tool.py` files in those configured namespace roots register tools, not agents.

## Inheritance

Authored agents are sparse by default. Unlike synthesised defaults, they do not copy a flow's LLM or tool defaults into their own stored fields.

Current inheritance rules are:

- `flow`: inherited from `extends` when omitted
- `llm_profile`: inherited when omitted
- `hooks`: inherited when omitted; explicit lists replace the parent list
- `skills`: inherited when omitted; explicit lists replace the parent list
- `tools`: inherited when omitted; explicit lists replace the parent list
- `extra_prompts`: appended after parent `extra_prompts`
- `inline_prompt`: appended after parent `inline_prompt`
- `tool_confirmation.default`: child overrides parent when present
- `tool_confirmation.overrides`: merged with child keys winning

If an agent inherits from an unknown base or an inheritance cycle is detected, the loader keeps the raw file but drops the unresolved effective agent from runtime use.

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

- `<resource_root>/<name>.agent.md` and `<resource_root>/<name>.agent.yaml` for flat workspace agent profiles
- `<resource_root>/agents/**/*.agent.md` and `<resource_root>/agents/**/*.agent.yaml` for recursive workspace agent collections
- `<resource_root>/agent.<group>/**/*.agent.md` and `<resource_root>/agent.<group>/**/*.agent.yaml` for typed grouped agent collections; Markdown agent files default their name to `<group>.<relative_name>` when `name` is omitted
- `<resource_root>/llm-profiles/` for workspace LLM profile YAML files
- `<resource_root>/<name>.hook.md` and `<resource_root>/<name>.hook.yaml` for flat direct hook assets
- `<resource_root>/hooks/**/*.hook.md` and `<resource_root>/hooks/**/*.hook.yaml` for recursive hook collections
- `<resource_root>/hook.<group>/**/*.hook.md` and `<resource_root>/hook.<group>/**/*.hook.yaml` for typed grouped hook collections; hook files default their name to `<group>.<relative_name>` when `name` is omitted
- `<resource_root>/<name>.tool.md` and `<resource_root>/<name>.tool.py` for flat direct tool assets under `resource_root.<name>`; the default `.pocketcode/` root is also aliased under `workspace`
- `<resource_root>/tools/**/*.tool.md` and `<resource_root>/tools/**/*.tool.py` for recursive tool collections
- `<resource_root>/tool.<group>/**/*.tool.md` and `<resource_root>/tool.<group>/**/*.tool.py` for typed grouped tool collections; Markdown tool files default their name to `<group>.<relative_name>` when `name` is omitted
- `<resource_root>/<name>.prompt.md` for shared direct prompts and prompt fallback resolution
- `<resource_root>/prompts/**/*.md` for prompt collections resolved by dotted relative path
- `<resource_root>/skill.<name>/SKILL.md` as a single-skill alias beside `<resource_root>/skills/<name>/SKILL.md`
- `runtime.workspace_paths[*]` for namespace-owned executable `*.md` flows, `*.prompt.md` prompts, and `*.tool.py` tools from plain namespace roots such as `.github/`

Built-in `core` is loaded from the package resource root under `pocketcode/.pocketcore/`. The package-owned Python implementations for that namespace live under `pocketcode/core_tools/`.

Current hook phases are `before_turn`, `before_llm`, `after_llm`, `before_tool`, `after_tool`, and `after_turn`. Hook phase bodies are StackVM source.

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

## Workspace Agent Schema

Workspace agents are loaded from all discovered flat agent files plus recursive `agents/` and typed `agent.<group>/` collections in every resource root. New or cloned agents are saved into the primary resource root using the grouped `agent.<group>/...` convention. For a name like `review.safe`, the default path is `<resource_root>/agent.review/safe.agent.md` or `.yaml`; for a single-segment name like `review`, the default path is `<resource_root>/agent.review/review.agent.*`.

Markdown-backed agents use the same fields, with YAML front matter for structured keys and the Markdown body as `inline_prompt`.

### Self-Contained Hybrid Agents

Agent profiles in Markdown can also define their own executable flow logic directly in the same file. These are called **self-contained hybrid agents**.

If a Markdown agent profile includes any flow-definition fields (such as `vm_source`, `vm_entry`, or `module`), the system automatically:
1.  Compiles an embedded `FlowDefinition` from those fields.
2.  Registers it in the flow registry under `agents.<agent_name>` (unless an explicit `flow` is provided).
3.  Configures the agent profile to target this embedded flow.

This allows creating a fully functional agent—logic and personality—in a single `.md` file.

Example self-contained StackVM agent:

```md
---
name: echo-bot
description: A simple bot that echoes the request.
execution_mode: vm
vm_entry: main
---

You are an echo bot.

```vm
[ request answer ] "main" define
```
```

Notes:
- Self-contained agents require at least one `vm_*` field or `module`/`entry_fn`.
- The CLI command `/agent new self-md <name>` creates a scaffold for this kind of profile-scoped hybrid agent.
- For new executable authoring that should be shared as a runtime asset rather than a profile overlay, prefer a Markdown VM file in a configured workspace namespace root or flat namespace-pack root instead.

Example YAML form:

```yaml
name: my-agent
flow: core.react
description: Optional description
llm_profile: fast-review
hooks:
  - workspace.memory.default
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

Example inheriting YAML form:

```yaml
name: my-agent-safe
extends: my-agent
hooks:
  - workspace.shortcut.cache
tools:
  - core.read_file
tool_confirmation:
  default: confirm
```

Equivalent Markdown form:

```md
---
name: my-agent
flow: core.react
llm_profile: fast-review
tools:
  - core.read_file
extra_prompts:
  - prompts/review.md
---
Review changes conservatively and call out regressions first.
```

Notes:

- `flow` is required unless `extends` is present or the Markdown file is self-contained.
- `extends` is accepted in YAML and Markdown and is stored internally as `base_agent`.
- `hooks` omitted means inherit the parent hook list or synthesised default chain.
- `skills` omitted means fall back to the global Textual skill selection order.
- `tools` omitted means inherit the target flow tool surface.
- agent-facing runtime controls such as flow selection, tool listing, and per-agent LLM overrides normalize typed `flow:` or `agent:` references before registry lookup.
- `extra_prompts` entries beginning with `prompt:` resolve through the prompt registry.
- path-based `extra_prompts` are resolved relative to the profile file first, then through namespace and resource-root prompt fallback roots. Paths such as `prompts/review.md` are also accepted when the resource-root prompt fallback path is active.
- workspace Markdown-backed agent bodies are loaded into `inline_prompt` after include and import expansion using the same workspace prompt registry and `<resource_root>/prompts/` fallback resolution used by workspace Markdown flows.
- workspace-backed agent files now validate and normalize typed refs while loading; malformed `flow`, `extends`, `hooks`, `tools`, or `extra_prompts` entries cause that agent file to be skipped with a warning instead of failing later during runtime resolution.
- workspace Markdown agent edits and clones now validate `include` and `import` prompt references before reload through the shared engine asset API, so broken prompt-file references fail during authoring instead of only after a later registry reload.
- that same pre-reload validation now resolves the target `flow`, validates `extends` against currently loaded executable or authored agents, and checks explicit `hooks`, `tools`, and `prompt:` entries in `extra_prompts` against the live registries.
- when a workspace-backed agent profile is saved or updated, registry-backed `flow`, `tools`, and `tool_confirmation.overrides` entries are written back in canonical dotted form, while `prompt:` sources remain typed and plain path-based prompt entries remain plain paths; Markdown-backed profiles are preserved as Markdown on save.
- after the engine has loaded flows, tools, and prompts, authored agents are resolved through inheritance and validated again against the live registries; resolvable tool refs are canonicalized, invalid prompt-resource refs are removed with a warning, and agents whose effective target flow is no longer available are dropped from the loaded registry.

## Inline Flow Default Agent Block

New built-in and workspace-authored flows should define any inline default profile directly in self-contained Markdown.

Example:

```yaml
flows:
  myflow:
    module: myflow.py
    entry_fn: create_flow
    default_agent:
      name: myflow-safe
      description: Safe review agent
      llm_profile: fast-review
      skills:
        - python-testing
      tools:
        - core.read_file
      tool_confirmation:
        default: confirm
```

## CLI Surface

The current agent command surface is:

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

- `/agent list` shows named authored agents and excludes synthesised flow defaults.
- `/agent show` defaults to the active agent when no name is supplied.
- editing commands apply only to workspace-backed agents; plugin and synthesised defaults must be cloned first.

Agent command shortcuts:

- `/ag` -> `/agent`
- `/ap` -> `/agent`

Flow selection can optionally activate a profile:

```text
/flow <flow_name|auto> [--agent <agent_name>]
```

## Textual UI Notes

Current Textual agent-system controls include:

- `F3` opens the editor picker for agent config, LLM config, tool selection, tool policies, and workspace flow or tool assets
- `F4` opens the clone picker for agent and LLM configs plus workspace flow or tool assets
- `F6` opens the Control Center for active profile selection, LLM override, skills, tool selection, tool policy editing, selection presets, session confirmation, and system settings
- the inspector exposes inline `Skills` and `Allowed Tools` selection lists, each with a `Save` button that writes the current selection into the active workspace agent profile file
- inline inspector tool and skill selections are session-scoped effective runtime overrides, not persistent `pocketcode.yml` state
- new sessions seed those runtime overrides from the active agent profile file before any session-specific changes are applied
- tool entries are grouped hierarchically and can be toggled at either the group or leaf level
- searchable selection popups support `Ctrl+Down`, `Ctrl+Up`, and `Space`
- tool groups are derived from the tool source path under `tools/`
- last-used profile and LLM choices are still persisted for Textual startup convenience
- saving inspector skills writes `skills` in the active workspace agent profile file and clears any matching legacy Textual override state
- saving inspector tools writes `tools` in the active workspace agent profile file and clears any matching legacy Textual override state
- `Reset` clears the current session override and `Save as Default` writes the current selection into config
- editing a plugin or synthesised profile from the Textual UI requires cloning it to a workspace-backed profile first

Current skill fallback order is:

1. active session per-profile skill override
2. active profile file `skills`
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
| `pocketcode/core/stackvm_loader.py` | StackVM source assembly from inline, module, and file-backed flow fields |
| `pocketcode/core/stackvm_parser.py` | StackVM tokenization and AST parsing before execution |
| `pocketcode/core/stackvm_expander.py` | StackVM compile-time macro expansion over parsed AST |
| `pocketcode/core/stackvm_validator.py` | StackVM executable-AST validation, compile-only form checks, and source-level authoring warnings for legacy tool-loop and prompt-route patterns |
| `pocketcode/core/agent_stack_vm.py` | StackVM execution engine, built-in words, and runtime host words |
| `pocketcode/core/tool_runtime.py` | confirmation policy resolution and allowlist enforcement |
| `pocketcode/cli/command_handler.py` | `/flow` and `/agent` CLI surface |
| `pocketcode/cli/completers.py` | profile completion support |
| `pocketcode/cli/textual_app.py` | Stable Textual UI import surface and re-exports |
| `pocketcode/cli/textual_ui/` | Textual status bar, control surfaces, modal screens, and UI workflows |
| `tests/unit/test_agent_profile_manager.py` | manager unit tests |
| `tests/unit/test_agent_profile_resolution.py` | precedence and resolution tests |
