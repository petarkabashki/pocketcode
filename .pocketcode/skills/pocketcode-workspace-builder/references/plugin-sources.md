# Plugin Sources

Primary sources:
- `pocketcode/core/manifest_loader.py`
- `pocketcode/core/plugin_manager.py`
- `docs/plugin_architecture.md`
- `specs/003-unified-plugin-namespace/quickstart.md`

## Manifest rules

`manifest_loader.py` is the schema truth:
- the manifest file is `plugin.yaml`
- `schema_version: 1` is required
- `flows` is the canonical section
- legacy `agents` is only treated as a compatibility alias during load
- each flow must define both `module` and `entry_fn`

Valid top-level sections commonly used:
- `name`
- `description`
- `tools`
- `flows`
- `prompts`
- `llm_profiles`

## What `plugin_manager.py` actually registers

`PluginManager`:
- discovers plugin roots from the built-in plugin folder and `runtime.plugin_paths`
- supports manifest plugins and `get_plugin()` factory plugins
- registers tools, flows, prompts, and LLM profiles
- stores flows in `self.flows` and aliases them as `self.agents`
- resolves local tool names within the owning plugin first
- normalizes `plugin::tool` and `plugin.tool` references

Important behavior:
- prompt text is resolved during plugin load
- `flow_instance` is created eagerly by loading the referenced Python module and calling `entry_fn`
- flow metadata includes at least `plugin` and `plugin_root`
- `default_agent` or `default_agent_profile` blocks in a flow definition create plugin-provided composite agents

## Prompt handling inside plugins

Prompt files are resolved by `resolve_prompt_bundle()`:
- inline prompt fields are concatenated first
- prompt files are loaded after that
- `prompts:` is accepted as an alias for `prompt_files` in flow definitions
- prompt includes use `{{ include:path.md }}`

## Authoring checklist

When creating or editing a plugin:
1. Start with `plugin.yaml`.
2. Register tools with `file.py:ClassName` references.
3. Register flows with `module` and `entry_fn`.
4. Put prompt files inside the plugin where possible.
5. Use qualified cross-plugin names when referencing non-local tools or flows.
6. Add a plugin-local `agents/*.yaml` only when a named profile is needed.

## Good local references

Prefer:
- `read_file` when the tool is owned by the same plugin
- `core::read_file` or `core.read_file` for cross-plugin use

Avoid:
- ambiguous bare names when multiple plugins can own the same tool
- repo-only references in prompts or manifests when the workspace may not contain the repo

