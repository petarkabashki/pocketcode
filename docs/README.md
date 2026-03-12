# PocketCoder Canonical Documentation

This `docs/` directory is the canonical documentation set for the current codebase.

Rules for maintaining documentation:

- Treat the codebase and `docs/` as the source of truth.
- When code and documentation disagree, fix `docs/` to match the code, or fix the code and update `docs/` in the same change.
- Treat `specs/` as historical design history and incremental change records. Specs can be useful for intent and context, but they are not authoritative once the implementation has moved on.
- Prefer documenting current runtime behavior, load order, precedence rules, and file formats over documenting planned features.

## Core Terms

- `vm program`: the preferred executable authoring unit for new work. In practice this is a self-contained Markdown file with StackVM plus optional sibling `*.tool.py` / `*.prompt.md` files or explicit relative `tool_files`.
- `flow`: the internal executable runtime unit registered by discovered namespaces and resource roots. Internally, flows are represented by `FlowDefinition`.
- `agent`: a named configuration overlay for a flow. Agents can override LLM selection, prompt additions, tool allowlists, and tool confirmation policy, and authored agents can inherit from other agents.
- `skill`: an additive session capability pack that can append prompt guidance and contribute tools.
- `workspace resources`: files under `.pocketcode/` that extend the runtime without changing package code.
- `workspace namespace`: a runtime namespace loaded either from a plain folder such as `.github/` or from a flat namespace-pack root such as `.pocketcode/`, where filenames carry the namespace prefix like `coder.coder.md` or `coder.git.tool.py`.

## Qualified Names

The registry's canonical qualified form is a dotted namespace such as `core.react` or `github.review`.

The registry uses dotted namespace ids such as `core.react` and `github.review`. Registry-backed surfaces also accept typed references such as `tool:core.read_file`, `flow:core.react`, `agent:core.react`, and `prompt:resource_root.pocketcode.review`.

## Documentation Map

- `agent_system.md`: agent model, schemas, inheritance, precedence, and control surfaces
- `architecture.md`: startup, loading, registries, execution loop, and precedence rules
- `configuration.md`: `pocketcode.yml`, discovered resource roots, namespace roots, and prompt loading
- `markdown_assets.md`: canonical syntax, locations, validation, and runtime behavior for Markdown-authored prompts, tools, flows, agents, and skills
- `cli.md`: startup flags, commands, aliases, and Textual controls
- `pocketflow_agents.md`: flow authoring and agent behavior
  - `stackvm_cookbook.md`: **canonical source for StackVM combinators, macros, and authoring patterns**. It now treats self-contained Markdown VM programs as the default and documents when extracting reusable VM modules is justified.
  - `stackvm_macros.md`: **canonical source for StackVM compile-time macro authoring**. Covers `defmacro`, `syntax-quote`, builtin macros, expansion metadata, and current limitations.
  - `stackvm_patterns.md`: groups checked-in StackVM examples by orchestration style. Use it to find example starting points once you understand the self-contained VM authoring model from `stackvm_cookbook.md`.
- `modes_and_skills.md`: current skill behavior and notes on the removed legacy mode surface
- `run_cancellation.md`: current cancellation model and managed subprocess behavior

Checked-in example assets live outside `docs/` under `examples/`. Current StackVM examples are `examples/stackvm_example/`, `examples/stackvm_handoff_example/`, `examples/stackvm_resilient_example/`, `examples/stackvm_config_router_example/`, `examples/stackvm_nested_router_example/`, `examples/stackvm_threshold_router_example/`, `examples/stackvm_parallel_map_example/`, `examples/stackvm_parallel_tool_map_example/`, `examples/stackvm_reduce_example/`, `examples/stackvm_reduce_tool_example/`, `examples/stackvm_reduce_numeric_example/`, `examples/stackvm_tool_normalize_example/`, `examples/stackvm_normalize_handoff_example/`, `examples/stackvm_normalize_ask_example/`, `examples/stackvm_normalize_confirm_example/`, `examples/stackvm_buttons_example/`, `examples/stackvm_radio_example/`, `examples/stackvm_prompt_return_example/`, `examples/stackvm_checklist_return_example/`, `examples/stackvm_structured_return_routing_example/`, `examples/stackvm_structured_return_finalize_example/`, `examples/stackvm_nested_structured_return_example/`, `examples/stackvm_nested_structured_return_routing_example/`, `examples/stackvm_checklist_handoff_example/`, `examples/stackvm_multistage_pipeline_example/`, and `examples/stackvm_macro_authoring_example/`.

## Practical Reading Order

1. Read `architecture.md` for the system model.
2. Read `agent_system.md` for agent behavior, inheritance, and precedence.
3. Read `configuration.md` for workspace setup and discovery behavior.
4. Read `markdown_assets.md` when working on any Markdown-authored asset.
5. Read `cli.md` for the user-facing control surface.
6. Read `pocketflow_agents.md`, `stackvm_patterns.md`, `stackvm_cookbook.md`, and `stackvm_macros.md` when changing runtime resources.
   For StackVM authoring, start with the self-contained VM sections in `stackvm_cookbook.md`, then use `stackvm_macros.md` for the compile-time surface and `stackvm_patterns.md` for example starting points.
7. Read `modes_and_skills.md` when working on skills or legacy mode migration.
8. Read `run_cancellation.md` when changing long-running tools or stop behavior.

## Historical Specs

Everything under `specs/` should be read as historical incremental design material.

- Use specs to understand why a change was introduced.
- Do not assume a spec still matches current code.
- If a spec disagrees with `docs/` or the implementation, the implementation and `docs/` win.
