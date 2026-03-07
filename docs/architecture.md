# Architecture

This document describes the current runtime architecture implemented in the repository.

## System Model

PocketCoder is a plugin-driven runtime with four distinct layers:

1. `FlowDefinition`: the executable runtime unit loaded from plugins.
2. `CompositeAgent` / agent profile: a named overlay for a flow.
3. `ModeDefinition`: a Markdown-authored overlay that resolves into an ephemeral active profile.
4. `SkillDefinition`: an additive session pack that extends prompts and tool availability.

The engine always executes a flow. Agent profiles, modes, and skills modify how that flow is invoked.

## Startup Sequence

Engine construction in `pocketcode.core.engine.PocketCodeEngine` follows this order:

1. Load `pocketcode.yml` from the workspace root.
2. Build `PluginManager` and load package plugins plus configured plugin roots.
3. Load workspace prompt and tool resources from `.pocketcode/prompts/` and `.pocketcode/tools/`.
4. Build `AgentManager` from loaded flows.
5. Load workspace modes from `.pocketcode/modes/`.
6. Load workspace skills from `.pocketcode/skills/`.
7. Load workspace LLM profiles from `.pocketcode/llm-profiles/`.
8. Build `LlmRouter`, `ToolRuntime`, and `AgentRuntime`.
9. Restore persisted Textual selection state such as active profile, mode, skills, and last-used tool overrides.

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
- `default_agent_profile`

### `CompositeAgent`

Also defined in `pocketcode/core/runtime_models.py`.

Important fields:

- `name`, `flow`
- `description`
- `llm_profile`
- `inline_prompt`
- `extra_prompts`
- `tools`
- `tool_confirmation`
- `source`, `source_path`

### `ModeDefinition`

Loaded by `ModeManager` from Markdown files in `.pocketcode/modes/`.

Modes choose a target flow or base agent profile and then layer:

- optional `llm_profile`
- optional tool selection override
- optional inline prompt body
- optional `extra_prompts`
- optional tool confirmation overrides

### `SkillDefinition`

Loaded by `SkillManager` from `.pocketcode/skills/<name>/SKILL.md`.

Skills contribute:

- inline prompt text
- extra prompt files
- references to already-registered tools
- tool modules loaded from `tools/*.py`

## Registries And Names

`NamespaceRegistry` stores resources in canonical `plugin.resource` form.

- Qualified lookup accepts both `plugin.resource` and `plugin::resource`.
- Unqualified lookup is allowed only when the name is unique, otherwise it raises `RegistryError`.
- Internally, flows, tools, and prompts are all stored in the same qualified naming scheme.

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

The workspace-local extension surface is:

- `.pocketcode/plugins/`
- `.pocketcode/agents/`
- `.pocketcode/llm-profiles/`
- `.pocketcode/modes/`
- `.pocketcode/skills/`
- `.pocketcode/tools/`
- `.pocketcode/prompts/`

Workspace prompts are registered under the `workspace` namespace. Workspace tools are auto-discovered from public exports and are also registered under `workspace`.

## Execution Loop

`AgentRuntime.run()` executes a turn loop over the active flow:

1. Resolve the active flow from `shared_store["active_agent"]`.
2. Run configured pre-handlers.
3. Execute one of:
   - a programmatic PocketFlow flow instance
   - a deterministic Python handler
   - a composite flow handoff plan
   - an LLM turn
4. Run configured post-handlers.
5. Interpret the resulting transition.
6. If the transition requests a tool call, run `ToolRuntime.execute_tool()`.
7. If the transition requests a handoff, update active flow and handoff context.
8. Continue until final answer, user question, error, or step limit.

Programmatic PocketFlow flows are loaded from manifest `module` plus `entry_fn` and stored as `flow_instance`.

## Shared Store

The shared store is the runtime session state passed through a request.

Common runtime-managed keys include:

- `active_agent`
- `active_agent_profile`
- `active_skills`
- `dynamic_llm_overrides`
- `pending_tool`
- `pending_handoff_agent`
- `_handoff_stack`
- `agent_trace`
- `llm_usage_totals`
- `llm_cost_usd_total`
- `_registry`

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

## Agent Profile Precedence

`AgentManager` loads profiles in this effective precedence order:

1. plugin-declared default agent blocks and plugin-local `agents/*.yaml`
2. workspace `.pocketcode/agents/*.yaml`
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