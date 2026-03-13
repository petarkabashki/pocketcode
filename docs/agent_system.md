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

The current codebase still uses `AgentProfile` and "profile" in some APIs and UI labels. In the canonical model, that term means a named agent overlay. The preferred authored executable shape for new work is a self-contained Markdown agent that carries both prompt/personality and executable VM logic in one file.

An authored agent can control:

- which LLM profile to use
- which reusable hooks are mixed into runtime lifecycle phases
- which tools are permitted
- which extra prompt files are appended to the flow prompt
- which default and per-tool confirmation policies apply

Every flow gets a synthesised default agent at load time. Authored agents can extend that default or any other agent.

## Agent Fields

The runtime model is `CompositeAgent` in `pocketcode/core/runtime_models.py`.

Current fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | none | Unique agent identifier |
| `flow` | `str` | none | Qualified target flow name; accepts canonical dotted ids and typed `flow:` or `agent:` forms |
| `base_agent` | `str \| None` | `None` | Optional parent agent/profile name to inherit from; Markdown and YAML also accept `extends` |
| `description` | `str` | `""` | Human-readable description |
| `llm_profile` | `str \| None` | `None` | LLM profile override |
| `inline_prompt` | `str` | `""` | Inline prompt text appended after the flow prompt |
| `extra_prompts` | `List[str]` | `[]` | Additional prompt references; each entry may be a file path or a `prompt:` resource reference |
| `hooks` | `List[str] \| None` | `None` | Ordered hook refs mixed into the agent lifecycle; `None` means inherit |
| `skills` | `List[str] \| None` | `None` | Default enabled skills; `None` means use global skill defaults |
| `tools` | `List[str] \| None` | `None` | Tool allowlist; `None` means inherit flow tool surface |
| `commands` | `List[AgentCommand]` | `[]` | Declarative command aliases exported by the agent |
| `tool_confirmation` | `dict` | `{}` | Confirmation defaults and per-tool overrides |
| `source` | `str` | `"synthesised"` | One of `synthesised`, `namespace`, or `workspace`; `namespace` marks agent overlays synthesized from configured namespace roots and non-workspace resource roots |
| `source_path` | `Path \| None` | `None` | Source file path for workspace-backed agents |

- `tools` entries resolve through the shared registry, so they accept canonical dotted ids and typed `tool:` references.
- `hooks` entries resolve through the shared registry, so they accept canonical dotted ids and typed `hook:` references.
- registry references must use canonical dotted ids such as `core.read_file`

Current `commands` entries are declarative aliases with these fields:

- `name`: slash-command name exported by the active agent provider
- `target`: either a shell-like command string to delegate to, such as `memory compact 1`, or a structured target mapping
- `visibility`: one of `exported`, `delegated`, or `private`; only `exported` is currently surfaced by the active-agent provider
- `description`: optional human-readable help text
- `capabilities`: optional capability names added to the delegated command context
- `payload_schema`: optional structured input contract for the command
- `result_schema`: optional structured result contract for the command
- `policy`: optional command-policy metadata such as confirmation expectations

Current structured target mappings support:

- `kind: command`
  - `command`: shell-like delegated command string
- `kind: agent_command`
  - `agent`: target agent/profile name
  - `command`: target declared command name on that agent
  - `visibility`: optional target-lookup visibility; defaults to `delegated`
- `kind: local_handler`
  - `handler`: deterministic handler name resolved by the engine for the active agent
  - `command`: optional logical target label; currently defaults to the handler name when omitted

Current visibility semantics are:

- `exported`: exposed by the active-agent provider and reachable from slash-command dispatch
- `delegated`: not exposed as a slash command, but reachable through the engine's active-agent command invocation API
- `private`: not exposed as a slash command and only reachable when the caller explicitly performs a private-visibility lookup

## Source And Precedence

Agents are loaded through `AgentManager` with this effective precedence:

1. workspace agent profiles from discovered resource roots, with new writes defaulting to grouped `agent.<group>/` paths
2. synthesised defaults built from flow definitions

On name collision, the higher-precedence source wins.

Configured namespace roots from `runtime.workspace_paths` are still not part of the authored-agent overlay search path. Their executable Markdown assets register flows in `WorkspaceCatalog`; self-contained `.agent.md` files in those roots therefore become executable catalog entries first, and `AgentManager` then synthesizes or resolves overlays for them. Matching `.tool.py` files in those configured roots register tools.

## Inheritance

Authored agents are sparse by default. Unlike synthesised defaults, they do not copy a flow's LLM or tool defaults into their own stored fields.

Current inheritance rules are:

- `flow`: inherited from `extends` when omitted
- `llm_profile`: inherited when omitted
- `hooks`: inherited when omitted; explicit lists replace the parent list
- `skills`: inherited when omitted; explicit lists replace the parent list
- `tools`: inherited when omitted; explicit lists replace the parent list
- `commands`: merged by command `name`, with child declarations replacing parent declarations of the same name
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

The authored-agent system uses these workspace paths:

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
- `<resource_root>/skills/<name>/SKILL.md` for skill bundles
- `runtime.workspace_paths[*]` for namespace-owned executable `*.md` and `*.agent.md` programs, `*.prompt.md` prompts, and `*.tool.py` tools from plain namespace roots such as `.github/`

Built-in `core` is loaded from the package resource root under `pocketcode/.pocketcore/`. The package-owned Python implementations for that namespace live under `pocketcode/core_tools/`.

Current hook phases are `before_turn`, `before_llm`, `after_llm`, `before_tool`, `after_tool`, and `after_turn`. Hook phase bodies are StackVM source.

The current StackVM host surface for hooks and VM-backed flows also includes active saved-session transcript access:

- `active-session-transcript` pushes the active saved session transcript as a list of transcript-entry mappings
- `active-session-transcript-text` pops `keep_last` and pushes a compact `Role: content` text block for the last `N` transcript entries

This enables reusable memory hooks that append recent chat history to prompt context without hardcoding memory logic into a specific flow.

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

### Self-Contained Markdown Agents

Markdown agents can also define their own executable flow logic directly in the same file. This is the canonical vm-first authoring path.

If a Markdown agent file includes any flow-definition fields, or fenced `vm` / `stackvm` blocks, the system automatically:
1.  Compiles an embedded `FlowDefinition` from those fields.
2.  Registers it in the flow registry under `agents.<agent_name>` for workspace agent collections, or under `<namespace>.<agent_name>` for configured namespace roots, unless an explicit `flow` is provided.
3.  Configures the agent to target this embedded flow.

This allows creating a fully functional agent in a single `.md` file.

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
- Self-contained agents require at least one `vm_*` field, a fenced `vm` or `stackvm` block, or `module`/`entry_fn`.
- The CLI command `/agent new self-md <name>` creates a scaffold for this kind of self-contained agent.
- Overlay-only agents are still supported, but new executable authoring should prefer the self-contained Markdown form.

Example YAML form:

```yaml
name: my-agent
flow: core.react
description: Optional description
llm_profile: fast-review
hooks:
  - resource_root.pocketcode.memory.chat_history
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
  - resource_root.pocketcode.shortcut.cache
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
- the workspace includes a reusable `resource_root.pocketcode.memory.chat_history` hook that appends the last six saved-session transcript entries to `formatted_cli_context` during `before_turn`; attach it to any agent whose runtime already consumes that context field, such as `core.react`

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
- editing commands apply only to workspace-backed agents; built-in resource-root agents and synthesised defaults must be cloned first.

Agent command shortcuts:

- `/ag` -> `/agent`
- `/ap` -> `/agent`

Flow selection can optionally activate a profile:

```text
/flow <flow_name|auto> [--agent <agent_name>]
```

## Textual UI Notes

Current Textual agent-system controls include:

- `F5` opens the runtime view picker for `chat` and `run`
- `F10` toggles the right-side details panel
- the details panel is read-only and shows runtime summary, session context, session history, and prompt sources
- agent switching, profile editing, tool allowlist editing, and other authored-agent mutations are no longer exposed through the Textual shell
- authored agent configuration remains file-backed; use workspace files or provider/admin command surfaces rather than the runtime UI

Current skill fallback order is:

1. active session per-profile skill override
2. active profile file `skills`
3. active session global skill override
4. Textual `default_skills`

## Command Providers

PocketCoder's slash-command parser is still global, but agent-scoped command handling now has an engine-level extension surface.

The current runtime exposes two provider hooks on `PocketCodeEngine`:

- `get_active_agent_command_provider()`
- `get_root_command_provider()`

Those hooks return `CommandProvider` implementations defined by `pocketcode/core/command_runtime.py`. A provider publishes `CommandSpec` records and handles invocation through structured `CommandContext` and `CommandResult` models.

Current provider precedence for non-shell commands is:

1. active-agent provider
2. root provider

This means agent-specific or subagent-backed commands can be encapsulated behind the active agent's provider without replacing the shared slash-command parser.

The intended command ownership split is:

- shell/app commands stay in the CLI layer
- root provider commands cover shared runtime capabilities that should behave like a base global agent surface
- active-agent providers can export agent-specific commands
- subagents can define their own command surfaces privately or as delegated ACP actions, but they should only become user-facing slash commands when the parent or root provider explicitly re-exports them

The current provider runtime does not yet add canonical new agent fields for authored command definitions. The implemented hook is the engine/provider contract that later metadata-backed command exports will target.

The current root provider already behaves like a base global command host for two deterministic command families:

- `memory`
- `checkpoint`

Those commands are not tied to any specific authored agent profile. They are exported by the engine's root provider so future active agents can extend or override them while the shared slash-command parser remains stable.

Capability scope currently works like this:

- interactive/root command execution gets the engine's default root command-capability set
- subagent or delegated execution gets no implicit root capabilities
- a parent must pass explicit capabilities into the delegated command context if a child is meant to invoke protected root-provider actions such as `memory.trim`, `memory.compact`, or `checkpoint.restore`

That model keeps "base global" commands available at the top level while still allowing stricter subagent boundaries.

The currently implemented active-agent command surface is metadata-driven:

- when the active agent profile contains `commands`, the engine builds an active-agent `CommandProvider` from those declarations
- each exported declaration delegates to its `target` command string through the same provider runtime used by root commands
- structured `agent_command` targets delegate to another named agent profile's declared command without switching the globally active profile
- structured `local_handler` targets dispatch to deterministic handler callables supplied by the engine for the active agent profile
- self-targeting command aliases are rejected

When an agent command runs, the engine now also builds an internal `CommandInvocation` envelope that carries:

- normalized command name
- positional args
- structured `payload`
- caller agent
- active agent
- session id
- requested visibility
- delegated capabilities
- arbitrary metadata for nested delegation

That envelope is not yet persisted or exposed as a public protocol surface, but it is now the canonical internal shape passed through nested agent-command and local-handler dispatch.

Command handlers can now also return structured `data` alongside plain-text `output`. The current CLI still renders the text path, but the runtime contract is now ready for typed command-result handling.

Current authored command-schema semantics:

- `payload_schema` and `result_schema` are canonical metadata fields carried through the runtime on `AgentCommand` and `CommandSpec`
- `payload_schema` is now enforced for structured payloads passed through active-agent command invocation
- `result_schema` is now enforced against `CommandResult.data` returned through active-agent command invocation
- current enforcement supports the implemented subset: `type`, `properties`, `required`, and primitive property types
- `policy` is descriptive metadata today; it is carried through command loading and discovery so future policy enforcement can use a stable authored field
- the engine also exposes a visibility-aware active-agent invocation path for non-exported `delegated` and `private` declarations
- `delegated` and `private` declarations are therefore usable today through engine/ACP-style callers even though only `exported` declarations participate in slash-command discovery

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
| `pocketcode/core/stackvm_validator.py` | StackVM executable-AST validation, compile-only form checks, and source-level authoring warnings for manual tool-loop and prompt-route patterns |
| `pocketcode/core/agent_stack_vm.py` | StackVM execution engine, built-in words, and runtime host words |
| `pocketcode/core/tool_runtime.py` | confirmation policy resolution and allowlist enforcement |
| `pocketcode/cli/command_handler.py` | `/flow` and `/agent` CLI surface |
| `pocketcode/cli/completers.py` | profile completion support |
| `pocketcode/cli/textual_ui/__init__.py` | Textual UI package export surface |
| `pocketcode/cli/textual_ui/` | Textual status bar, control surfaces, modal screens, and UI workflows |
| `tests/unit/test_agent_profile_manager.py` | manager unit tests |
| `tests/unit/test_agent_profile_resolution.py` | precedence and resolution tests |
