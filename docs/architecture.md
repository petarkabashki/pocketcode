# Architecture

This document describes the current runtime architecture implemented in the repository.

## System Model

PocketCoder is a resource-root runtime with four distinct layers:

1. `FlowDefinition`: the executable runtime unit loaded from workspace namespaces and direct resource roots.
2. `CompositeAgent` / agent: a named agent definition or overlay for a flow, optionally inheriting from another agent.
3. `SkillDefinition`: an additive session pack that extends prompts and tool availability.
4. `HookDefinition`: a reusable VM-backed lifecycle overlay discovered from resource roots and referenced by agents.

Markdown-authored flows, tools, prompts, agents, and skills are compilation inputs, not a separate runtime layer. They are normalized into the same registries and runtime models used by direct resource folders and Python factories referenced from Markdown. See `markdown_assets.md` for the asset-level syntax and validation model.

The engine always executes a flow. Agents, hooks, and skills modify how that flow is invoked. In practice, new executable authoring should prefer self-contained Markdown agents, but the runtime still materializes them as a flow plus an agent record internally.

For new executable authoring, the canonical shape is a self-contained Markdown agent with VM blocks plus optional sibling `.tool.py` / `.prompt.md` helpers. `FlowDefinition` remains the internal runtime model, but the public authoring surface is agent-first.

Built-in core tools have a single canonical package location:

- `pocketcode/.pocketcore/` is the built-in package resource root.
- `pocketcode/core_tools/` contains the package-owned Python implementations used by the built-in `core` namespace.
- `.pocketcode/` is the primary direct resource-root surface for flow, tool, prompt, and agent assets and is also aliased under the `workspace` namespace. New workspace agent writes default to grouped `agent.<group>/` paths under that root.

Core filesystem-style tools in `pocketcode/core_tools/filesystem.py` and staged file-edit helpers in `pocketcode/core_tools/file_ops.py` are constrained to the current workspace root. The engine publishes that root into each request's shared store, and any path that resolves outside it is rejected before read, write, mkdir, glob, selection, extract, or staged-apply work is performed.

Workspace-owned shim modules are not part of the supported runtime surface. Workspace migration removes them before startup.

## Workspace Root Versus Resource Root

PocketCoder distinguishes between:

1. `workspace_root`: the operational project boundary used for config, external runtime state, and filesystem safety.
2. `resource_root`: a discoverable folder inside the workspace that can contribute direct flat resources.
3. `catalog`: the in-memory runtime snapshot built from all discovered resource roots plus configured namespace roots.

`resource_root` is the filesystem primitive. `WorkspaceCatalog` is the compiled runtime view produced from those roots. The engine executes against the catalog so lookups, precedence handling, and registry qualification do not require repeated filesystem traversal.

The runtime auto-discovers resource roots from top-level hidden directories whose names begin with `.pocket` and that contain canonical flat convention files such as `*.md`, `*.hook.md`, `*.hook.yaml`, `*.tool.md`, `*.prompt.md`, or `*.tool.py`, resource collections such as `agents/`, `hooks/`, `prompts/`, `tools/`, `skills/`, or `llm-profiles/`, or typed collection folders such as `agent.<group>/`, `hook.<group>/`, and `tool.<group>/`.

Examples:

- `.pocketcode/`
- `.pocketflow/`

When `.pocketcode/` exists, it remains the primary save location for workspace-backed authored assets. Runtime state now defaults to sibling workspace-root folders such as `.pocketstate/` and `.pockethist/`.

## Startup Sequence

Engine construction in `pocketcode.core.engine.PocketCodeEngine` follows this order:

1. Load `pocketcode.yml` from the workspace root.
2. Build `WorkspaceCatalog` and load discovered package/workspace resource roots plus configured namespace roots.
3. Resolve `runtime.workspace_paths`, treating each entry as either one VM-first namespace root or one flat namespace-pack root.
4. Load direct prompt, hook, tool, and executable resources from all discovered resource roots, including Markdown-backed hook assets, tools, flows, and self-contained executable agents.
5. Build `AgentManager` from loaded flows.
6. Load skills from all discovered resource roots.
7. Load workspace LLM profiles from all discovered resource roots.
8. Resolve loaded agents through inheritance, then validate effective agents and skills against the populated registries, canonicalizing resolvable refs and pruning the remaining invalid static targets.
9. Build `LlmRouter`, `ToolRuntime`, and `AgentRuntime`.
10. Restore persisted Textual selection state such as active profile, skills, and last-used tool overrides.

This creates a two-phase validation model:

- load-time syntax validation in the individual loaders
- engine-time existence validation after flows, tools, prompts, and workspace resources are all registered

Markdown asset loading participates in the same two phases:

- Markdown files are expanded and compiled into structured definitions during loader execution.
- registry-backed refs inside those compiled definitions are then canonicalized and validated against the live registries.

That shared model applies across prompt files, Markdown hook definitions, Markdown tool definitions, Markdown flow definitions, Markdown agent definitions, and skills.

Within a resource root, canonical flat files still load exactly as before. Workspace agents still load as overlays from agent locations, and self-contained Markdown agents in those same locations now also contribute executable catalog entries when they carry flow fields. The additional folder conventions are:

- `prompts/**/*.md` registers workspace prompts by relative dotted path, for example `prompts/review.md -> resource_root.pocketcode.review` and `prompts/shared/base.md -> resource_root.pocketcode.shared.base`
- `hooks/**/*.hook.md` and `hooks/**/*.hook.yaml` load workspace hook definitions; hook files default their name from the relative dotted path under `hooks/`
- `tools/**/*.tool.md` and `tools/**/*.tool.py` register direct workspace tools; Markdown tool wrappers default their tool name from the relative dotted path under `tools/`
- `agents/**/*.agent.md` and `agents/**/*.agent.yaml` load workspace agent profiles; Markdown agent profiles default their name from the relative dotted path under `agents/`
- `hook.<group>/` behaves like an extra hook collection root; hook files inside it default to `<group>.<relative_name>`
- `tool.<group>/` behaves like an extra tool collection root; Markdown tool wrappers inside it default to `<group>.<relative_name>`
- `agent.<group>/` behaves like an extra agent collection root; Markdown agent profiles inside it default to `<group>.<relative_name>`
- skills load from `skills/<name>/SKILL.md`

For executable Markdown specifically, the loader now has two execution outcomes:

- if the compiled definition provides `module` plus `entry_fn`, PocketCoder loads that Python PocketFlow factory
- if the compiled definition carries StackVM source fields such as `vm_source`, `vm_module`, or `vm_file`, PocketCoder registers a VM-backed flow with `execution_mode: vm`

That applies both to direct `*.md` flow assets and to self-contained `*.agent.md` assets that carry embedded execution fields or fenced VM blocks.

Markdown flow definitions may also declare `tool_files`. Each entry is resolved relative to the Markdown file first, loaded as a Python tool module, and registered into the same namespace before the flow definition is finalized. When `tool_files` is present and the flow does not declare `tools`, the exported tool names become the flow's base tool list automatically. When `tool_files` and prompt-file fields are omitted, the loader also looks for sibling `<name>.tool.py` and `<name>.prompt.md` files beside the Markdown program and wires them in automatically.

StackVM-backed flows execute against the same shared-store contract used by handwritten PocketFlow flows, including `_tool_runtime`, `pending_handoff_agent`, `final_answer`, `question_to_ask`, `results`, and other runtime-managed keys.

## Command Runtime Layers

Slash-command parsing still starts in `pocketcode/cli/command_handler.py`, but the runtime now also exposes a small command-provider abstraction for non-shell commands.

Implemented command-runtime pieces:

- `pocketcode/core/command_runtime.py` defines `CommandSpec`, `CommandContext`, `CommandResult`, and the `CommandProvider` protocol
- `PocketCodeEngine.build_command_context(...)` builds the command invocation context from the active engine/session state plus the current CLI context
- `PocketCodeEngine.get_active_agent_command_provider()` and `PocketCodeEngine.get_root_command_provider()` are the current extension points for agent-scoped and root-scoped command providers
- `PocketCodeEngine.invoke_registered_command(...)` enforces provider precedence and capability checks before invoking a registered provider command

Current non-shell provider precedence is:

1. active-agent provider
2. root provider

Shell/app commands such as `/help`, `/quit`, `/reload`, `/debug`, `/stop`, and `/cancel` remain direct CLI concerns and are not modeled as agent commands.

This split is intentional:

- shell commands control the application surface
- provider-backed commands are the extensible path for future root-agent, active-agent, and delegated subagent command surfaces
- capability enforcement remains inside the engine/service boundary rather than inside the CLI parser

The currently implemented root provider exposes deterministic session-state operations:

- `memory`: inspect, trim, or compact the active saved-session transcript
- `checkpoint`: save, list, inspect, and restore named snapshots of the active session state plus transcript

These root-provider commands are implemented directly against engine/session services rather than through an LLM-backed agent. That keeps mutation deterministic while still using the same provider dispatch path that future active-agent and subagent command exports will use.

The active-agent provider path is also implemented for declarative command aliases stored on the resolved active agent profile:

- agent `commands` metadata is loaded through the normal YAML and Markdown agent loaders
- inheritance merges command declarations by command name, with child declarations replacing parent declarations of the same name
- the active-agent provider currently exposes only declarations whose visibility is `exported`
- exported declarations delegate through the same engine/provider runtime used by root commands
- a declaration target may be another command path, another named agent profile's declared command, or an active-agent local handler supplied by the engine

Non-exported agent commands now have a separate invocation path:

- `invoke_active_agent_command(..., visibility="delegated")` resolves delegated declarations without making them slash-visible
- `invoke_active_agent_command(..., visibility="private")` resolves private declarations only for explicit private lookups

This keeps slash-command discovery limited to exported commands while still giving parent agents or future ACP layers a concrete way to call delegated or private agent-local command surfaces.

Under the hood, command dispatch now also builds a small ACP-style invocation envelope for internal use:

- `CommandInvocation` carries the normalized command name, positional args, caller agent, active agent, session id, requested visibility, delegated capabilities, and arbitrary metadata
- `CommandInvocation` also carries a structured `payload` mapping for typed command input
- active-agent command dispatch passes that envelope through command-path, named-agent-command, and local-handler target execution
- local handlers therefore receive both the existing command context and the structured invocation payload

Command results now also support a structured `data` mapping alongside plain-text `output`.

Authored agent command metadata now also flows through runtime command specs:

- `payload_schema`
- `result_schema`
- `policy`

These fields are descriptive contract metadata at the moment. They are loaded, inherited, serialized, and exposed on runtime command specs, but the current runtime does not yet reject invocations that fail those schemas.

The current enforced fields are:

- `payload_schema`: validated against the structured invocation payload before invoking the target command path, named-agent command, or local handler
- `result_schema`: validated against `CommandResult.data` after the target returns

`policy` is still descriptive metadata only.

This is still an internal runtime model rather than an external wire protocol, but it gives the command system an explicit contract for future ACP transport, tracing, policy decisions, and typed command payload/result flows. The shared CLI has correspondingly been narrowed to a smaller inspection/control shell surface; mutable authoring flows are expected to move through provider commands or direct workspace file edits rather than bespoke shell handlers.

Current command capabilities are also enforced at the engine boundary:

- interactive/root command invocations receive a default root capability set
- delegated or subagent invocations receive no implicit capabilities unless the caller passes them explicitly
- individual root-provider subcommands perform their own finer-grained checks such as `memory.read`, `memory.trim`, `memory.compact`, `checkpoint.read`, `checkpoint.write`, and `checkpoint.restore`

This means a subagent can only invoke the more destructive root-provider operations when its parent explicitly grants the matching capability in the command context.

## Key Runtime Types

### `FlowDefinition`

Defined in `pocketcode/core/runtime_models.py`.

Important fields:

- `name`, `description`
- `llm_profile`
- `tools`
- `handoff_agents`
- `execution_mode`
- `deterministic_handler`
- `composite_agents`
- `system_prompt`, `prompt_sources`
- `pre_handlers`, `step_handlers`, `post_handlers`
- `handoff_policies`, `default_handoff_policy`
- `module`, `entry_fn`, `flow_instance`
- `vm_entry`, `vm_module`, `vm_modules`
- `vm_file`, `vm_files`, `vm_source`
- `default_agent_profile`

### `CompositeAgent`

Also defined in `pocketcode/core/runtime_models.py`.

Important fields:

- `name`, `flow`, `base_agent`
- `description`
- `llm_profile`
- `inline_prompt`
- `extra_prompts`
- `hooks`
- `skills`
- `tools`
- `tool_confirmation`
- `source`, `source_path`

### `SkillDefinition`

Loaded by `SkillManager` from discovered resource roots.

Skills contribute:

- inline prompt text
- extra prompt files
- references to already-registered tools
- tool modules loaded from `tools/*.tool.py`

Skills validate static tool and prompt references during manager load itself because the engine passes the live tool and prompt registries into that loader.

After managers load, the engine still performs a narrow normalization pass over loaded overlays:

- profile and skill refs that can be resolved globally are canonicalized to registry form
- context-dependent unqualified refs can remain deferred for per-run resolution

## Registries And Names

`NamespaceRegistry` stores resources in canonical dotted namespace form such as `core.react` or `github.review`.

- Qualified lookup uses dotted namespace ids.
- Typed lookup also accepts `tool:...`, `flow:...`, `agent:...`, `hook:...`, and `prompt:...`; the type prefix is stripped before registry resolution.
- Unqualified lookup is allowed only when the name is unique, otherwise it raises `RegistryError`.
- Internally, flows, hooks, tools, and prompts are all stored in the same qualified naming scheme.

Reference parsing is centralized in `pocketcode/core/reference_syntax.py`.

- `ResourceReference` is the shared parsed representation used for typed-kind detection, canonical target normalization, and qualified versus unqualified checks.
- manifest loading, workspace agent loading, markdown skill loading, registry normalization, prompt-resource resolution, and engine-side post-load pruning now consume this parsed form instead of duplicating string-splitting logic.
- runtime tool lookup, allowlist checks, and confirmation-policy maps normalize canonical and typed tool ids through the same parser-backed path.
- persistence paths reuse the same normalization layer, so workspace agent profile files, saved session confirmation overrides, persistent tool-confirmation config, and Textual selection presets are written back with canonical dotted registry ids instead of mixed older forms.
- `normalize_registry_reference()` remains the strict shared entrypoint for canonical registry ids.

## Catalog Discovery

`WorkspaceCatalog` loads resources from:

1. the built-in package resource root under `pocketcode/.pocketcore/`
2. paths listed in `runtime.workspace_paths`
3. workspace direct resources under discovered resource roots such as `.pocketcode/`

`runtime.workspace_paths` is the canonical executable discovery surface. Each entry is either one workspace namespace root or one flat namespace-pack root for VM-first self-contained Markdown programs.

Built-in `core` no longer uses that manifest path. It is loaded through the same workspace-namespace Markdown and `.tool.py` discovery model used for user-authored namespace assets.

There are two supported configured namespace shapes:

- a plain namespace root such as `.github/`, where the folder name becomes the namespace
- a flat namespace-pack root such as `.pocketcode/`, where filenames carry the namespace prefix

Inside a plain namespace root:

- `*.prompt.md` registers prompt text under `<namespace>.<name>`
- `*.tool.py` registers tool exports under `<namespace>.*`
- executable `*.md` files compile directly into a `FlowDefinition` under `<namespace>.<name>`
- when a Markdown program omits explicit prompt/tool file wiring, sibling `<name>.prompt.md` and `<name>.tool.py` files are auto-attached

Inside a flat namespace-pack root:

- `<namespace>.<name>.md` compiles into `<namespace>.<name>`
- `<namespace>.<name>.prompt.md` registers prompt `<namespace>.<name>`
- `<namespace>.<helper>.tool.py` registers tool exports under `<namespace>.*`

Namespace folders and flat namespace-pack roots do not require manifest files.

## Workspace Resources

Each discovered resource root contributes a workspace-owned extension surface:

- flat convention files such as `<resource_root>/<flow>.md`, `<resource_root>/<flow>.prompt.md`, `<resource_root>/<flow>.tool.py`, `<resource_root>/<hook>.hook.md`, `<resource_root>/<hook>.hook.yaml`, `<resource_root>/<tool>.tool.md`, `<resource_root>/<agent>.agent.md`, and `<resource_root>/<agent>.agent.yaml`
- `<resource_root>/llm-profiles/`
- `<resource_root>/skills/`

Runtime session state is persisted under `<runtime.storage.session_state_dir>/sessions/`, which defaults to `.pocketstate/sessions/` relative to the workspace root.

Direct resource-root prompts, hooks, tools, and flows are registered under resource-root namespaces such as `resource_root.pocketcode`.

Configured workspace namespace roots and flat namespace-pack roots sit alongside that direct resource-root surface. They register their own flows, prompts, and `.tool.py` helpers under their declared namespace and are not auto-written by the workspace asset editors.

Saved sessions are runtime-generated JSON snapshots managed by `pocketcode/core/session_manager.py` and scoped to the current workspace root.
Each saved session record now also persists debugger breakpoint labels and a derived breakpoint count so debugger intent survives session resume and UI restart.

## Execution Loop

`AgentRuntime.run()` executes a turn loop over the active flow:

1. Resolve the active flow from `shared_store["active_agent"]`.
2. Run configured pre-handlers.
3. Execute one of:
   - a programmatic PocketFlow flow instance
   - a StackVM-backed flow
   - a deterministic Python handler
   - a composite flow handoff plan
   - an LLM turn
4. Run configured post-handlers.
5. Interpret the resulting transition.
6. If the transition requests a tool call, run `ToolRuntime.execute_tool()`.
7. If the transition requests a handoff, update active flow and handoff context.
8. Continue until final answer, user question, error, or step limit.

## Hook Runtime

Hooks are reusable `HookDefinition` assets discovered from resource roots, not from configured `runtime.workspace_paths` namespace roots.

Current hook phases are:

- `before_turn`
- `before_llm`
- `after_llm`
- `before_tool`
- `after_tool`
- `after_turn`

Agents opt into hooks through their `hooks` list. During runtime, `AgentRuntime` resolves those refs through the hook registry and executes any matching phase body as StackVM against the same shared store and host services used by VM-backed flows.

Hooks are intended to shape execution around core primitives, not replace the flow graph itself. They can mutate shared state, derive prompt context, request tools or handoffs, or short-circuit with a final answer through the normal VM host words and transition contract.

During request execution, `PocketCodeEngine.start_request()` now wraps the runtime event handler with a request-scoped observer in `pocketcode/core/runtime_observability.py`. That observer annotates emitted lifecycle events with stable step metadata and accumulates a structured step timeline for the completed run summary.

When `start_request(..., debug=True)` is used, the engine also enables the request `RunHandle`'s cooperative debugger. That debugger pauses the worker thread after queueing selected completed or instantaneous runtime-step events, while exposing a live snapshot callback back into the current shared store.

Tool results with `success: false` are kept in `last_tool_result` and do not automatically terminate the run. Flows may inspect the failure and decide whether to retry, answer, or hand off. Runtime errors are reserved for malformed tool requests, missing tool targets, unhandled exceptions, and other engine-level failures.

Programmatic PocketFlow flows are loaded from manifest `module` plus `entry_fn` and stored as `flow_instance`.

StackVM-backed flows are resolved from VM source metadata on the flow definition. At runtime, `AgentRuntime` assembles inline and file-backed VM source through `pocketcode/core/stackvm_loader.py`, parses it through `pocketcode/core/stackvm_parser.py`, collects non-fatal source authoring warnings plus executable-AST validation through `pocketcode/core/stackvm_validator.py`, expands compile-time macros through `pocketcode/core/stackvm_expander.py`, injects the same prompt/tool/LLM services used by PocketFlow agents, and runs the selected StackVM entry word through `pocketcode/core/agent_stack_vm.py` when configured. Because `AgentRuntime.run()` remains synchronous, VM execution moves to a dedicated worker thread when the caller is already inside a running asyncio event loop.

The `/stackvm run` and `/stackvm debug` CLI commands use that same runtime path. Registered StackVM flows execute directly against their loaded `FlowDefinition`, while standalone scripts under `<primary_resource_root>/vm/` are wrapped into a temporary synthetic `FlowDefinition` for the duration of the command so tool calls, handoffs, result routing, and final-answer handling still use the normal execution loop.

LLM decision parsing uses a shared YAML-mapping parser. It accepts fenced YAML blocks and also trims leading prose before the first YAML key so responses like `Here is the YAML:` followed by a valid mapping do not abort the run.

## Shared Store

The shared store is the runtime session state passed through a request.

Common runtime-managed keys include:

- `active_agent`
- `active_agent_profile`
- `active_skills`
- `active_session_id`
- `active_session_title`
- `dynamic_llm_overrides`
- `filesystem_root`
- `pending_tool`
- `pending_handoff_agent`
- `run_id`
- `workspace_root`
- `_handoff_stack`
- `agent_trace`
- `llm_usage_totals`
- `llm_cost_usd_total`
- `_registry`
- `_runtime_observability`

`workspace_root` and `filesystem_root` currently resolve to the same absolute directory: the process working directory used to start PocketCoder. Core filesystem and staged-edit tools use `filesystem_root` as their allowlisted boundary.

Programmatic PocketFlow flows also receive runtime helpers such as `_llm_router`, `_tool_runtime`, `_agent_llm_profile`, `_agent_system_prompt`, and `_agent_tool_definitions`.

The request-scoped observability helper stores:

- `event_count`: total runtime events seen for the request
- `steps`: ordered structured steps for agent turns, LLM calls, tool calls, handoffs, handoff returns, and runtime errors
- `active_steps`: in-flight step bookkeeping used to pair started and completed events

The request `RunHandle` also owns the cooperative debugger state:

- whether debugging is enabled for the request
- whether the run is currently paused at a debugger boundary
- the paused runtime event payload
- the current debugger mode (`step` versus `continue`)
- an optional step budget for counted stepping such as `next 5`
- an optional one-shot until predicate for commands such as `until node review_route` or `until when pending_tool.name == "core.write_file"`
- an optional persistent breakpoint list, each with an id, label, and predicate
- an engine-provided live snapshot callback used by the CLI debugger surfaces
- interface-specific debugger controls layered on top of the shared `RunHandle` operations such as `step_debugger()`, `continue_debugger()`, breakpoint creation, and breakpoint clearing
- Textual maps those controls onto both button actions and selected run-inspector breakpoint blocks so individual saved breakpoints can be cleared without raw command input
- the active session snapshot now includes canonical debugger breakpoint labels, and `start_request(..., debug=True)` restores those saved labels onto each new request `RunHandle` before execution begins

StackVM-backed runs publish runtime-step events through the same shared observability path used by agent turns, tool calls, and handoffs. The debugger and run summary operate on those runtime-step boundaries rather than on a separate graph-flow node model.

`PocketCodeEngine._build_run_summary()` copies that state into the persisted `last_run_summary` as:

- `runtime_event_count`
- `step_count`
- `steps`

Each public step entry currently includes:

- `index`
- `kind`
- `label`
- `status`
- `parent_step_index`
- `duration_ms`
- `summary`
- compact `details`

## Resolution Orders

### LLM profile resolution

Current order in `AgentRuntime._resolve_llm_profile()`:

1. CLI per-flow override
2. config per-flow override
3. CLI global override
4. dynamic runtime override
5. active agent profile `llm_profile`
6. flow default `llm_profile`
7. `default_llm_profile` from shared store
8. router default profile

### Prompt composition

Current effective prompt composition is:

1. flow `system_prompt`
2. active profile `inline_prompt`
3. active profile resolved `extra_prompts`
4. enabled skill inline prompts
5. enabled skill resolved `extra_prompts`

Prompt file includes are expanded before the flow `system_prompt` is stored.

### Enabled skill resolution

Current enabled-skill resolution order is:

1. active session per-profile skill override
2. active profile file `skills`
3. active session global skill override
4. Textual `default_skills`

### Tool availability

Current effective tool set is:

1. flow tool list resolved from flow and resource-root definitions
2. filtered by active profile `tools` when a tool allowlist is present
3. extended by enabled skill references to already-registered tools
4. extended by enabled skill-provided tool modules

### Tool confirmation policy

Current order in `ToolRuntime._resolve_confirmation_policy()` is:

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

Before confirmation is evaluated, the runtime denies any tool outside the active allowlist.

When a confirmation prompt returns a scope choice, `ToolRuntime.execute_tool()` applies it as follows:

1. `once`: approve only the current tool call
2. `session`: update the engine's session confirmation overrides and persist them into the active saved session snapshot
3. `always`: update persisted `runtime.tool_confirmation.tool_policies` in `pocketcode.yml`
4. `deny`: fail closed for the current call

## Session Persistence

`PocketCodeEngine` creates an active saved session during initialization if none exists for the resource_root.pocketcode.

Current behavior:

- each request gets a generated `run_id` in the shared store
- request lifecycle hooks append user and assistant or system transcript entries to the active saved session after each run
- session snapshots persist active agent, active profile, enabled skills, global LLM override, session-scoped profile tool/skill overrides, and session confirmation overrides
- session snapshots also persist debugger breakpoint labels so future debug runs can restore the same breakpoint set onto the next `RunHandle`
- starting a new session creates a new saved-session file and switches the active session pointer
- starting a new session clears prior session-only tool and skill overrides, then reseeds the new session from the active agent/profile file state
- resuming a session restores runtime selections from the saved snapshot and marks the active session as history-backed
- deleting a session is blocked when the target matches the active session id
- clearing saved sessions removes only non-active saved sessions
- the engine exposes saved-session detail and breakpoint-pruning helpers so `/session show <id>`, `/session clear-breakpoints <id> --yes`, and the Textual Control Center can inspect or clear persisted debugger breakpoints without resuming the session first

## Agent Profile Precedence

`AgentManager` loads profiles in this effective precedence order:

1. workspace resource-root agent profiles from `<resource_root>/*.agent.yaml` and `<resource_root>/*.agent.md`
2. synthesised defaults built from each flow definition

Name collisions keep the higher-precedence source.

## Hot Reload

`WorkspaceCatalog.load()` rebuilds registries and swaps them atomically through `RegistryHolder`.

- New sessions see the new snapshot immediately.
- Existing sessions keep the registry snapshot captured at session start.

## Workspace-Only Discovery

The canonical loader path is now workspace-only:

- executable flows come from namespace Markdown and direct resource-root Markdown
- Python flow factories are referenced from Markdown through `module` plus `entry_fn`
- tools are discovered by `*.tool.py` convention or through direct resource-root tool folders
- documentation in `docs/` describes this workspace-only model
