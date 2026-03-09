# PocketCoder Canonical Documentation

This `docs/` directory is the canonical documentation set for the current codebase.

Rules for maintaining documentation:

- Treat the codebase and `docs/` as the source of truth.
- When code and documentation disagree, fix `docs/` to match the code, or fix the code and update `docs/` in the same change.
- Treat `specs/` as historical design history and incremental change records. Specs can be useful for intent and context, but they are not authoritative once the implementation has moved on.
- Prefer documenting current runtime behavior, load order, precedence rules, and file formats over documenting planned features.

## Core Terms

- `flow`: the executable runtime unit registered by the plugin system. Internally, flows are represented by `FlowDefinition` and are the primary execution surface.
- `agent profile`: a named configuration overlay for a flow. Profiles can override LLM selection, prompt additions, tool allowlists, and tool confirmation policy.
- `mode`: a Markdown-authored session overlay that resolves into an ephemeral agent profile.
- `skill`: an additive session capability pack that can append prompt guidance and contribute tools.
- `workspace resources`: files under `.pocketcode/` that extend the runtime without changing package code.

## Qualified Names

The registry's canonical qualified form is `plugin.resource`.

The runtime also accepts `plugin::resource` in user-facing configuration, manifests, and commands, then normalizes it to `plugin.resource` internally. Registry-backed surfaces also accept typed references such as `tool:core.read_file`, `flow:core.react`, `agent:core.react`, and `prompt:resource_root.pocketcode.review`. This documentation uses `plugin.resource` when describing registry behavior and may show legacy or typed forms where that matches the current user-facing surface.

## Documentation Map

- `agent_system.md`: agent profile model, schemas, precedence, and control surfaces
- `architecture.md`: startup, loading, registries, execution loop, and precedence rules
- `configuration.md`: `pocketcode.yml`, `.pocketcode/`, discovery controls, and prompt loading
- `markdown_assets.md`: canonical syntax, locations, validation, and runtime behavior for Markdown-authored prompts, tools, flows, agents, modes, and skills
- `cli.md`: startup flags, commands, aliases, and Textual controls
- `plugin_architecture.md`: plugin discovery, manifest schema, flow fields, and prompt/tool registration
- `pocketflow_agents.md`: flow authoring and agent profile behavior
	- `stackvm_cookbook.md`: **canonical source for StackVM helper conventions and architectural split**. Contains copyable authoring snippets for common runtime patterns, including the shared example-helper conventions used by the checked-in payload-driven VM examples. Refer to this doc for the definitive list and description of normalization/formatting helpers and the `vm/common.vm` vs `vm/router.vm` split.
	- `stackvm_patterns.md`: groups checked-in StackVM examples by orchestration style. For helper conventions and architectural split, always refer to `stackvm_cookbook.md` as canonical. Use this doc to find example starting points and orchestration patterns.
- `modes_and_skills.md`: Markdown-authored runtime overlays and skill-provided tools
- `run_cancellation.md`: current cancellation model and managed subprocess behavior

Checked-in example assets live outside `docs/` under `examples/`. Current StackVM examples are `examples/stackvm_review_plugin/`, `examples/stackvm_handoff_plugin/`, `examples/stackvm_resilient_plugin/`, `examples/stackvm_config_router_plugin/`, `examples/stackvm_nested_router_plugin/`, `examples/stackvm_threshold_router_plugin/`, `examples/stackvm_parallel_map_plugin/`, `examples/stackvm_parallel_tool_map_plugin/`, `examples/stackvm_reduce_plugin/`, `examples/stackvm_reduce_tool_plugin/`, `examples/stackvm_reduce_numeric_plugin/`, `examples/stackvm_tool_normalize_plugin/`, `examples/stackvm_normalize_handoff_plugin/`, `examples/stackvm_normalize_ask_plugin/`, `examples/stackvm_normalize_confirm_plugin/`, `examples/stackvm_buttons_plugin/`, `examples/stackvm_radio_plugin/`, `examples/stackvm_prompt_return_plugin/`, `examples/stackvm_checklist_return_plugin/`, `examples/stackvm_structured_return_routing_plugin/`, `examples/stackvm_structured_return_finalize_plugin/`, `examples/stackvm_nested_structured_return_plugin/`, `examples/stackvm_nested_structured_return_routing_plugin/`, `examples/stackvm_checklist_handoff_plugin/`, and `examples/stackvm_multistage_pipeline_plugin/`.

## Practical Reading Order

1. Read `architecture.md` for the system model.
2. Read `agent_system.md` for agent-profile behavior and precedence.
3. Read `configuration.md` for workspace setup and discovery behavior.
4. Read `markdown_assets.md` when working on any Markdown-authored asset.
5. Read `cli.md` for the user-facing control surface.
    6. Read `plugin_architecture.md`, `pocketflow_agents.md`, `stackvm_patterns.md`, and `stackvm_cookbook.md` when changing runtime resources.
    	For StackVM example cleanup or authoring, **start with the helper-conventions and architectural split sections in `stackvm_cookbook.md` (canonical)** before editing individual example routers. Use `stackvm_patterns.md` to find orchestration patterns and example starting points.
7. Read `modes_and_skills.md` when working on session overlays.
8. Read `run_cancellation.md` when changing long-running tools or stop behavior.

## Historical Specs

Everything under `specs/` should be read as historical incremental design material.

- Use specs to understand why a change was introduced.
- Do not assume a spec still matches current code.
- If a spec disagrees with `docs/` or the implementation, the implementation and `docs/` win.