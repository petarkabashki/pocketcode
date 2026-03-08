# Plugin Architecture

This document describes the current plugin model implemented by `PluginManager` and `ManifestLoader`.

## Canonical Plugin Model

The canonical plugin format is `plugin.yaml` with `schema_version: 1`.

Plugins can contribute:

- tools
- flows
- prompts
- LLM profiles
- plugin-local agent profiles in `agents/*.yaml` and `agents/*.md`

Flows, tools, and plugin-local agent profiles may also be authored in Markdown and compiled into the same runtime objects used by the canonical loaders. See `markdown_assets.md` for the canonical shared Markdown syntax and validation rules.

## Discovery Roots

Current plugin discovery sources are:

1. package plugins under `pocketcode/plugins/`
2. extra plugin roots listed in `runtime.plugin_paths`
3. nested `plugins/` folders inside each discovered resource root such as `.pocketcode/plugins/` or `.pocketflow/plugins/`

The common workspace setup is still to point `runtime.plugin_paths` at `.pocketcode/plugins`, but direct resource-root plugin folders are now discovered automatically.

## Supported Plugin Loading Forms

`PluginManager` supports three loading paths:

1. factory plugin: a plugin root with `__init__.py` exporting `get_plugin(config)`
2. manifest plugin: a plugin root with `plugin.yaml`
3. legacy compatibility plugin: a plugin root with `agent.yaml`

If a plugin root contains `__init__.py`, the factory loading path is attempted before manifest loading.

## Canonical Manifest Layout

Example:

```yaml
schema_version: 1
name: my_plugin
description: Example plugin

tools:
  read_notes: tools/notes.py:ReadNotesTool
  search_notes: tools/search_notes.md

prompts:
  system: prompts/system.md

llm_profiles:
  fast:
    provider: gemini
    model: gemini-3.1-flash-lite-preview

flows:
  analyst:
    description: Analyze workspace notes
    markdown: flows/analyst.md
    llm_profile: fast
    tools:
      - read_notes
      - core.read_file
      - tool:resource_root.pocketcode.shared_check
    prompt_files:
      - prompts/system.md
```

Flow-level `tools` entries resolve through the shared registry. They accept bare local names, canonical `plugin.resource`, legacy `plugin::resource`, and typed `tool:` references.

Workspace Markdown flow edits and clones now validate those `tools` references, `handoff_agents`, `composite_agents`, and prompt-bundle entries against the live registries before reload, in addition to validating executable Mermaid or DOT graph topology.

Internally, these manifest-facing string forms are parsed through the shared `ResourceReference` model in `pocketcode/core/reference_syntax.py`, so tool, flow, agent, and prompt refs now share the same normalization and kind-validation path.

That normalization now happens during manifest loading as well as during later registry-backed validation, so the effective loaded flow definitions already carry canonical dotted tool, handoff, and composite-agent refs plus canonical `prompt:` resource refs before plugin registration finishes.

Malformed typed references in flow manifests are rejected during manifest loading. For example, using `prompt:` inside a flow `tools:` list or `tool:` inside `prompt_files:` raises a schema error before the plugin is registered.

Once all plugins and direct resource-root assets are loaded, PocketCoder also validates registry-backed flow references against the populated registries. Missing tool, handoff, composite-agent, or prompt-resource targets are logged once and removed from the effective loaded definition.

## Manifest Keys

Top-level keys currently used by the loader:

- `schema_version`
- `name`
- `description`
- `tools`
- `flows`
- `prompts`
- `llm_profiles`

Legacy top-level keys such as `components`, `workflows`, `node_definitions`, and `modes` are not part of the canonical model and trigger warnings when present.

## Tool Registration

Manifest `tools` is a mapping of local name to `path.py:ObjectName`.

It also accepts a Markdown definition file path.

Example:

```yaml
tools:
  search_code: tools/search.py:SearchCodeTool
  summarize_notes: tools/summarize_notes.md
```

Loaded tool implementations may be:

- `BaseTool` subclasses
- `BaseTool` instances
- plain callables

After registration, the canonical qualified name is `plugin.tool`.

Markdown tool files are compiled first, then their `handler` field is resolved through the same `path.py:ObjectName` loader used by manifest string entries. The Markdown file supplies metadata such as description, schema, timeout, and execution mode; the underlying Python handler remains the executable implementation.

## Flow Definitions

Each manifest flow becomes a `FlowDefinition`.

Required fields:

- `module`
- `entry_fn`

Those required fields may be supplied either directly in `plugin.yaml` or inside a Markdown flow definition referenced through `markdown:` or a `.md` `source:` value.

Important optional fields:

- `description`
- `llm_profile`
- `tools`
- `allowed_tools` as a compatibility alias for `tools`
- `handoff_agents`
- `execution_mode`
- `mode` as a compatibility alias for `execution_mode`
- `deterministic_handler`
- `handler` as a compatibility alias for `deterministic_handler`
- `composite_agents`
- `sub_agents` and `delegate_agents` as compatibility aliases
- `pre`, `pre_steps`
- `steps`, `exec`, `exec_steps`
- `post`, `post_steps`
- `handoff_policies`
- `default_handoff_policy`
- `system_prompt`, `prompt`
- `system_prompt_file`, `prompt_file`, `prompt_files`
- `prompts` as a compatibility alias for `prompt_files`
- `default_agent`, `default_agent_profile`

## Execution Modes

Current normalized flow execution modes are:

- `llm`
- `deterministic`
- `composite`

If `module` plus `entry_fn` loads a PocketFlow factory successfully, the resulting `flow_instance` is used directly for execution.

Markdown-authored flows do not introduce a second runtime. They compile into the same `FlowDefinition` structure before normal manifest normalization, prompt resolution, and PocketFlow factory loading continue.

## Markdown Asset Authoring

Plugin manifests may point at Markdown-authored tools, flows, and plugin-local agent profiles.

Current plugin-specific Markdown entry points are:

- `tools.<name>: tools/<name>.md`
- `flows.<name>.markdown: flows/<name>.md`
- `flows.<name>.source: flows/<name>.md`
- `<plugin>/agents/*.md`

Current plugin-specific behavior:

- Markdown tools compile metadata first, then resolve the required Python `handler`
- Markdown flows compile into ordinary `FlowDefinition` data before prompt resolution and registry normalization continue
- plugin-local Markdown agent profiles expand `include` and `import` directives in plugin context when plugin metadata provides a plugin name and root
- plugin `prompts/` directories participate in fallback resolution for path-based prompt includes referenced by plugin-local Markdown assets

For the shared Markdown syntax, graph-flow semantics, prompt include and import behavior, and workspace authoring validation, see `markdown_assets.md`.

## Prompt Resolution For Flows

`PluginManager._register_flow_definition()` resolves prompts through `resolve_prompt_bundle()`.

Supported prompt sources are:

- inline `system_prompt` or `prompt`
- file-based `system_prompt_file` or `prompt_file`
- file lists in `prompt_files`
- compatibility alias `prompts`

Explicit prompt resource references are also supported anywhere a prompt file reference is accepted.

Current supported forms are:

- `prompt:plugin.prompt_name`
- `prompt:resource_root.<root_name>.prompt_name`
- `prompt:<container>#<prompt_name>` which normalizes to `<container>.<prompt_name>`

Examples:

- `prompt:core.system`
- `prompt:resource_root.pocketcode.review.default`
- `prompt:resource_root.pocketcode#review.default`

If no explicit prompt file or prompt resource reference is provided, the loader also checks default prompt candidates:

- `prompts/flows/<flow_name>.md`
- `prompts/agents/<flow_name>.md`

Prompt files can use nested includes via:

```text
{{ include:path/to/file.md }}
```

## Prompt Registration

Top-level manifest `prompts` registers prompt files into the prompt registry.

Example:

```yaml
prompts:
  system: prompts/system.md
```

This registers the prompt as `plugin.system`.

## Inline Default Agent Block

A flow may declare a default agent profile inline through `default_agent`.

Example:

```yaml
flows:
  analyst:
    module: flows/analyst.py
    entry_fn: create_flow
    default_agent:
      name: analyst-safe
      description: Restrictive profile
      llm_profile: fast
      tools:
        - core.read_file
      tool_confirmation:
        default: confirm
```

The flow key and any nested profile `flow` target may be referenced through canonical `plugin.resource`, legacy `plugin::resource`, or typed `flow:` and `agent:` forms on user-facing surfaces.

This becomes the flow's `default_agent_profile` and participates in agent profile precedence.

## Plugin-Local Agent Profiles

Plugins may also define profile files under:

```text
<plugin>/agents/*.yaml
<plugin>/agents/*.md
```

Those files use the same schema as workspace agent profiles. Markdown-backed profile files use front matter plus a Markdown body just like workspace Markdown agent profiles.

Precedence is:

1. plugin-declared default agent and plugin-local `agents/*.yaml` or `agents/*.md`
2. workspace agent profiles
3. synthesised default built from the flow definition

## Factory Plugins

Factory plugins return a `Plugin` instance from `get_plugin(config)`.

That object can contribute:

- tools
- programmatic flows
- prompts
- metadata

Flow instances returned by factory plugins are wrapped into `FlowDefinition` objects with `is_programmatic=True`.

## Resource-Root Prompts, Tools, And Flows

Direct resource-root shared assets are not declared through plugin manifests.

- `<resource_root>/prompts/` files are auto-registered under `resource_root.<name>`
- `<resource_root>/tools/*.py` modules are auto-discovered and registered under `resource_root.<name>`
- `<resource_root>/tools/*.md` files are auto-discovered as Markdown-backed tools under `resource_root.<name>`
- `<resource_root>/flows/*.md` files are auto-discovered as Markdown-backed flows under `resource_root.<name>`

For backward compatibility, the default `.pocketcode/` resource root also exposes its direct prompts, tools, and Markdown flows under the legacy `workspace` namespace.

Built-in core tools are separate from these direct resource-root resources. Their canonical implementation lives under `pocketcode/plugins/core/tools/`, while `pocketcode/tools/` is retained as a compatibility import surface.

These are separate from manifest plugin loading, but they join the same global registries.

## Discovery Controls

Plugins and plugin-local resources can be skipped through:

- `.disabled` in any path component
- ignore rules from workspace-root `.pocketcodeignore`
- resource-root `.pocketcodeignore` when the plugin root itself lives under a discovered resource root

## Legacy `agent.yaml`

`agent.yaml` still has a compatibility shim, but it is not canonical.

Limitations of the shim:

- it logs deprecation warnings
- it cannot synthesize manifest-quality flow definitions without `module` plus `entry_fn`
- it should be treated as migration-only support

For current authoring, always use `plugin.yaml` with `schema_version: 1`.