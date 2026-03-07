# Plugin Authoring

Primary sources:
- `pocketcode/core/manifest_loader.py`
- `pocketcode/core/plugin_manager.py`
- `docs/plugin_architecture.md`
- `docs/pocketflow_agents.md`
- `specs/003-unified-plugin-namespace/quickstart.md`

## Canonical layout

Typical plugin layout:
```text
.pocketcode/plugins/my_plugin/
├── plugin.yaml
├── flows/
├── prompts/
├── tools/
└── agents/
```

## Manifest truths

From `manifest_loader.py`:
- `plugin.yaml` is required
- `schema_version: 1` is required
- `flows` must be a mapping
- each flow entry must contain `module` and `entry_fn`

Common flow fields loaded by `plugin_manager.py`:
- `description`
- `llm_profile`
- `tools`
- `handoff_agents`
- `prompts` or `prompt_files`
- `default_agent`

## Registration behavior

From `plugin_manager.py`:
- tools are registered under `plugin.tool`
- flows are registered under `plugin.flow`
- prompts are resolved eagerly and registered under `plugin.prompt`
- local tool refs are resolved within the plugin first
- `plugin::name` and `plugin.name` are normalized

## Editing rules

1. Change the manifest and the referenced files together.
2. Keep flow module paths relative to the plugin root.
3. Use local tool names for plugin-owned tools and qualified names for cross-plugin tools.
4. Keep plugin prompts inside the plugin unless they are intentionally shared.
5. Add plugin-local `agents/*.yaml` only for explicit named profiles.

