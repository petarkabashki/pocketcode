# Architecture

This document describes the current runtime architecture implemented in the repository.

## System Model

PocketCoder is a plugin-driven runtime with four distinct layers:

1. `FlowDefinition`: the executable runtime unit loaded from plugins.
2. `CompositeAgent` / agent profile: a named overlay for a flow.
3. `ModeDefinition`: a Markdown-authored overlay that resolves into an ephemeral active profile.
4. `SkillDefinition`: an additive session pack that extends prompts and tool availability.

Markdown-authored flows, tools, prompts, agent profiles, modes, and skills are compilation inputs, not a separate runtime layer. They are normalized into the same registries and runtime models used by manifest YAML and Python factories. See `markdown_assets.md` for the asset-level syntax and validation model.

The engine always executes a flow. Agent profiles, modes, and skills modify how that flow is invoked.

Built-in core tools have a single canonical package location:

- `pocketcode/plugins/core/tools/` contains the package-owned implementations and shared exports.
- `pocketcode/tools/` is a compatibility facade for older imports plus workspace-owned shim exports.
- `.pocketcode/tools/` remains the default direct resource-root tool surface and is also aliased under the legacy `workspace` namespace.

Core filesystem-style tools in `pocketcode/plugins/core/tools/filesystem.py` and staged file-edit helpers in `pocketcode/plugins/core/tools/file_ops.py` are constrained to the current workspace root. The engine publishes that root into each request's shared store, and any path that resolves outside it is rejected before read, write, mkdir, glob, selection, extract, or staged-apply work is performed.

Workspace-owned compatibility shims are loaded through the shared helper in `pocketcode/core/workspace_module_loader.py`.

## Workspace Root Versus Resource Root

PocketCoder distinguishes between:

1. `workspace_root`: the operational project boundary used for config, sessions, and filesystem safety.
2. `resource_root`: a discoverable folder inside the workspace that can contribute direct resources and nested plugins.

The runtime auto-discovers resource roots from top-level hidden directories whose names begin with `.pocket` and that contain at least one recognized resource collection such as `agents/`, `modes/`, `skills/`, `prompts/`, `tools/`, `flows/`, `plugins/`, or `llm-profiles/`.

Examples:

- `.pocketcode/`
- `.pocketflow/`

When `.pocketcode/` exists, it remains the primary save location for workspace-backed edits and runtime state.

## Startup Sequence

Engine construction in `pocketcode.core.engine.PocketCodeEngine` follows this order:

1. Load `pocketcode.yml` from the workspace root.
2. Build `PluginManager` and load package plugins plus configured plugin roots.
3. Load direct prompt, tool, and flow resources from all discovered resource roots, including Markdown-backed tools and flows.
4. Build `AgentManager` from loaded flows.
5. Load modes from all discovered resource roots.
6. Load skills from all discovered resource roots.
7. Load workspace LLM profiles from all discovered resource roots.
8. Validate loaded agent profiles, modes, and skills against the populated registries, canonicalizing resolvable refs and pruning or rebinding the remaining contextual targets.
9. Build `LlmRouter`, `ToolRuntime`, and `AgentRuntime`.
10. Restore persisted Textual selection state such as active profile, mode, skills, and last-used tool overrides.

This creates a two-phase validation model:

- load-time syntax validation in the individual loaders
- engine-time existence validation after flows, tools, prompts, and workspace resources are all registered

Markdown asset loading participates in the same two phases:

- Markdown files are expanded and compiled into structured definitions during loader execution.
- registry-backed refs inside those compiled definitions are then canonicalized and validated against the live registries.

That shared model applies across prompt files, Markdown tool definitions, Markdown flow definitions, Markdown agent profiles, modes, and skills.

For flow Markdown specifically, the loader now has three execution outcomes:

- if the compiled definition provides `module` plus `entry_fn`, PocketCoder loads that Python PocketFlow factory
- if those fields are absent but the Markdown metadata includes a supported Mermaid or DOT graph plus `nodes:` configuration, PocketCoder generates a deterministic PocketFlow `Flow` directly from the graph
- if the compiled definition carries StackVM source fields such as `vm_source`, `vm_module`, or `vm_file`, PocketCoder registers a VM-backed flow with `execution_mode: vm`

The generated graph flow path and StackVM flow path execute against the same shared-store contract used by handwritten PocketFlow flows, including `_tool_runtime`, `pending_handoff_agent`, `final_answer`, `question_to_ask`, `results`, and other runtime-managed keys.

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

- `name`, `flow`
- `description`
- `llm_profile`
- `inline_prompt`
- `extra_prompts`
- `skills`
- `tools`
- `tool_confirmation`
- `source`, `source_path`

### `ModeDefinition`

Loaded by `ModeManager` from Markdown files in discovered resource roots.

Modes choose a target flow or base agent profile and then layer:

- optional `llm_profile`
- optional tool selection override
- optional inline prompt body
- optional `extra_prompts`
- optional tool confirmation overrides

### `SkillDefinition`

Loaded by `SkillManager` from discovered resource roots.

Skills contribute:

- inline prompt text
- extra prompt files
- references to already-registered tools
- tool modules loaded from `tools/*.py`

Modes and skills now validate most static references during manager load itself because the engine passes the live flow, tool, prompt, and mode-agent profile lookups into those loaders.

After managers load, the engine still performs a narrow normalization pass over loaded overlays:

- modes are re-bound to the concrete target flow selected by either `mode.flow` or the resolved `mode.agent` base profile
- mode and skill refs that can be resolved globally are canonicalized to registry form
- context-dependent unqualified refs can remain deferred for per-run resolution

## Registries And Names

`NamespaceRegistry` stores resources in canonical `plugin.resource` form.

- Qualified lookup accepts both `plugin.resource` and `plugin::resource`.
- Typed lookup also accepts `tool:...`, `flow:...`, `agent:...`, and `prompt:...`; the type prefix is stripped before registry resolution.
- Unqualified lookup is allowed only when the name is unique, otherwise it raises `RegistryError`.
- Internally, flows, tools, and prompts are all stored in the same qualified naming scheme.

Reference parsing is centralized in `pocketcode/core/reference_syntax.py`.

- `ResourceReference` is the shared parsed representation used for typed-kind detection, canonical target normalization, and qualified versus unqualified checks.
- manifest loading, workspace agent loading, markdown mode and skill loading, registry normalization, prompt-resource resolution, and engine-side post-load pruning now consume this parsed form instead of duplicating string-splitting logic.
- runtime tool lookup, allowlist checks, and confirmation-policy maps also normalize legacy and typed tool ids through the same parser-backed path.
- persistence paths reuse the same normalization layer, so workspace agent profile files, saved session confirmation overrides, persistent tool-confirmation config, and Textual selection presets are written back with canonical dotted registry ids instead of mixed legacy forms.
- permissive compatibility callers that must not reject malformed legacy input now route through the same shared fallback helper in `reference_syntax` instead of re-implementing local `::` normalization branches.
- compatibility helpers such as `normalize_registry_reference()` remain available, but they are wrappers over the shared parser.

## Plugin Discovery

`PluginManager` loads resources from:

1. package plugins under `pocketcode/plugins/`
2. paths listed in `runtime.plugin_paths`
3. workspace resources under `.pocketcode/`

Package and external plugin roots may contain:

- `plugin.yaml`
- legacy `agent.yaml`
- `__init__.py` with `get_plugin(config)`

If a plugin root contains both `__init__.py` and `plugin.yaml`, the factory-based `get_plugin(config)` path is attempted first.

## Workspace Resources

Each discovered resource root contributes a workspace-owned extension surface:

- `<resource_root>/plugins/`
- `<resource_root>/agents/`
- `<resource_root>/llm-profiles/`
- `<resource_root>/modes/`
- `<resource_root>/skills/`
- `<resource_root>/tools/`
- `<resource_root>/flows/`
- `<resource_root>/prompts/`

Runtime session state is persisted under `<primary_resource_root>/state/sessions/`.

Direct resource-root prompts, tools, and flows are registered under resource-root namespaces. For backward compatibility, the default `.pocketcode/` resource root also exposes its direct prompts, tools, and Markdown flows under the legacy `workspace` namespace.

Saved sessions are runtime-generated JSON snapshots managed by `pocketcode/core/session_manager.py` and scoped to the current workspace root.

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

Tool results with `success: false` are kept in `last_tool_result` and do not automatically terminate the run. Flows may inspect the failure and decide whether to retry, answer, or hand off. Runtime errors are reserved for malformed tool requests, missing tool targets, unhandled exceptions, and other engine-level failures.

Programmatic PocketFlow flows are loaded from manifest `module` plus `entry_fn` and stored as `flow_instance`.

StackVM-backed flows are resolved from VM source metadata on the flow definition. At runtime, `AgentRuntime` assembles inline and file-backed VM source through `pocketcode/core/stackvm_loader.py`, parses it through `pocketcode/core/stackvm_parser.py`, collects non-fatal source authoring warnings plus executable-AST validation through `pocketcode/core/stackvm_validator.py`, expands compile-time macros through `pocketcode/core/stackvm_expander.py`, injects the same prompt/tool/LLM services used by PocketFlow agents, and runs the selected StackVM entry word through `pocketcode/core/agent_stack_vm.py` when configured. Because `AgentRuntime.run()` remains synchronous, VM execution moves to a dedicated worker thread when the caller is already inside a running asyncio event loop.

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

`workspace_root` and `filesystem_root` currently resolve to the same absolute directory: the process working directory used to start PocketCoder. Core filesystem and staged-edit tools use `filesystem_root` as their allowlisted boundary.

Programmatic PocketFlow flows also receive runtime helpers such as `_llm_router`, `_tool_runtime`, `_agent_llm_profile`, `_agent_system_prompt`, and `_agent_tool_definitions`.

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

1. flow tool list resolved from plugin definitions
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

`PocketCodeEngine` creates an active saved session during initialization if none exists for the workspace.

Current behavior:

- each request gets a generated `run_id` in the shared store
- request lifecycle hooks append user and assistant or system transcript entries to the active saved session after each run
- session snapshots persist active agent, active profile, active mode, enabled skills, global LLM override, session-scoped profile tool/skill overrides, and session confirmation overrides
- starting a new session creates a new saved-session file and switches the active session pointer
- starting a new session clears prior session-only tool and skill overrides, then reseeds the new session from the active agent/profile file state
- resuming a session restores runtime selections from the saved snapshot and marks the active session as history-backed
- deleting a session is blocked when the target matches the active session id
- clearing saved sessions removes only non-active saved sessions

## Agent Profile Precedence

`AgentManager` loads profiles in this effective precedence order:

1. plugin-declared default agent blocks and plugin-local `agents/*.yaml` or `agents/*.md`
2. workspace resource-root agent profiles from `<resource_root>/agents/*.yaml` and `<resource_root>/agents/*.md`
3. synthesised defaults built from each flow definition

Name collisions keep the higher-precedence source.

## Hot Reload

`PluginManager.load()` rebuilds registries and swaps them atomically through `RegistryHolder`.

- New sessions see the new snapshot immediately.
- Existing sessions keep the registry snapshot captured at session start.

## Legacy Compatibility

The runtime still contains compatibility behavior for legacy `agent.yaml` plugins, but that format is not the canonical model.

- `plugin.yaml` with `schema_version: 1` is the current authoritative manifest format.
- Legacy manifests may still load through a warning-emitting shim.
- Documentation in `docs/` describes the current canonical model, not the compatibility path.
