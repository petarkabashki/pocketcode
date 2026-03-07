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

The runtime also accepts `plugin::resource` in user-facing configuration, manifests, and commands, then normalizes it to `plugin.resource` internally. This documentation uses `plugin.resource` when describing registry behavior and may show `plugin::resource` where that matches the current user-facing examples.

## Documentation Map

- `agent_system.md`: agent profile model, schemas, precedence, and control surfaces
- `architecture.md`: startup, loading, registries, execution loop, and precedence rules
- `configuration.md`: `pocketcode.yml`, `.pocketcode/`, discovery controls, and prompt loading
- `cli.md`: startup flags, commands, aliases, and Textual controls
- `plugin_architecture.md`: plugin discovery, manifest schema, flow fields, and prompt/tool registration
- `pocketflow_agents.md`: flow authoring and agent profile behavior
- `modes_and_skills.md`: Markdown-authored runtime overlays and skill-provided tools
- `run_cancellation.md`: current cancellation model and managed subprocess behavior

## Practical Reading Order

1. Read `architecture.md` for the system model.
2. Read `agent_system.md` for agent-profile behavior and precedence.
3. Read `configuration.md` for workspace setup and discovery behavior.
4. Read `cli.md` for the user-facing control surface.
5. Read `plugin_architecture.md` and `pocketflow_agents.md` when changing runtime resources.
6. Read `modes_and_skills.md` when working on session overlays.
7. Read `run_cancellation.md` when changing long-running tools or stop behavior.

## Historical Specs

Everything under `specs/` should be read as historical incremental design material.

- Use specs to understand why a change was introduced.
- Do not assume a spec still matches current code.
- If a spec disagrees with `docs/` or the implementation, the implementation and `docs/` win.