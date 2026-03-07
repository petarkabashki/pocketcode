# PocketCoder Documentation

PocketCoder is an extensible terminal AI coding assistant built around PocketFlow.

## Topics

### Core Concepts
- [Architecture Overview](architecture.md) (Planned)
- [Prompt Engineering](prompts.md) (Planned)
- [Modes and Skills](modes_and_skills.md)
- [Run Cancellation](run_cancellation.md)

### Plugins and Flows
- [Plugin Architecture](plugin_architecture.md)
- [PocketFlow Agents](pocketflow_agents.md)
- [`Agent Profiles` quickstart](../specs/001-agent-default-profiles/quickstart.md)
- [Dynamic Tools](tools.md) (Planned)

## Quick Start

1. Configure your LLM provider in `pocketcode.yml`.
2. Create a plugin directory under `.pocketcode/plugins/my_plugin/`.
3. Add a `plugin.yaml` with `schema_version: 1` and a `flows:` block.
4. Execute your flow with:

   ```
   pocketcode --flow my_plugin.my_agent
   ```

## Plugin Authoring

Plugins follow the unified plugin model introduced in 003-unified-plugin-namespace:

- One directory, one manifest (`plugin.yaml`, `schema_version: 1`).
- Tools declared as `local_name: "file.py:ClassName"`.
- Flows declared with `module:` + `entry_fn:` pointing to a PocketFlow factory.
- Prompts declared with `local_name: "prompts/file.md"` and loaded into the prompt registry.
- All resources addressable as `plugin_name.resource_name`.

This repo also ships a workspace authoring plugin at
`.pocketcode/plugins/workspace_builder/`. Its `workspace_builder::plugin_builder`
agent is intended for creating and editing workspace plugin resources and
workspace-level assets such as `plugin.yaml`, `flows/`, `prompts/`, `agents/`,
`llm-profiles/`, `tools/`, and `.pocketcode/skills/`. The plugin carries its own authoring
reference prompt so it remains usable even when PocketCoder is run from a
workspace that does not contain this repository's source tree. It is now paired
with a workspace-builder skill pack under `.pocketcode/skills/` for deeper,
self-contained guidance on PocketFlow graphs, plugin authoring, profiles and
prompts, tools and runtime behavior, and workspace assets.

See the full walkthrough: [`specs/003-unified-plugin-namespace/quickstart.md`](../specs/003-unified-plugin-namespace/quickstart.md)
