# Markdown-Based Assets

This document is the canonical reference for PocketCoder's Markdown-authored assets.

PocketCoder does not run a second Markdown-specific runtime. Markdown files are authoring inputs that compile into the same prompt, tool, flow, agent-profile, and skill models used elsewhere in the system.

Use this document together with:

- `architecture.md` for startup order and registry behavior
- `configuration.md` for workspace and resource-root paths
- `agent_system.md` for agent-profile semantics
- `modes_and_skills.md` for skill behavior and legacy mode migration notes
- `cli.md` for `/asset` creation, editing, and cloning

## Supported Asset Kinds

PocketCoder currently uses Markdown for these asset surfaces:

| Kind | Current locations | Runtime result |
|------|-------------------|----------------|
| Prompt | `<resource_root>/*.prompt.md`, `<resource_root>/prompts/**/*.md`, namespace `*.prompt.md`, path-based prompt includes | prompt text plus source tracking |
| Tool | adjacent `*.tool.py` modules, `<resource_root>/*.tool.md`, `<resource_root>/tools/**/*.tool.md`, `<resource_root>/tools/**/*.tool.py`, `<resource_root>/tool.<group>/**/*.tool.md`, `<resource_root>/tool.<group>/**/*.tool.py` | wrapped executable tool metadata plus Python handler |
| Flow | namespace `*.md`, `<resource_root>/*.md` | `FlowDefinition` with either a loaded PocketFlow factory or StackVM program source |
| Agent profile | `<resource_root>/*.agent.md`, `<resource_root>/*.agent.yaml`, `<resource_root>/agents/**/*.agent.md`, `<resource_root>/agents/**/*.agent.yaml`, `<resource_root>/agent.<group>/**/*.agent.md`, `<resource_root>/agent.<group>/**/*.agent.yaml` | `CompositeAgent` / agent profile; may also include an embedded `FlowDefinition` for self-contained agents |
| Skill | `<resource_root>/skills/<name>/SKILL.md`, `<resource_root>/skill.<name>/SKILL.md` | `SkillDefinition` |

Discovered resource roots accept both root-local assets such as `review.md` and flat namespace-pack files whose filenames carry the namespace prefix such as `coder.coder.md` and `coder.git.tool.py`. They also accept collection folders for prompts, tools, agents, and skills. The default workspace `.pocketcode/` root and the built-in package root `pocketcode/.pocketcore/` both use that discovery model. `runtime.workspace_paths` is reserved for additional plain namespace roots with executable `*.md` files plus adjacent `*.tool.py` and `*.prompt.md` siblings.

Collection-folder naming rules:

- `prompts/<path>.md` registers prompt `<path>` with `/` converted to `.`
- `tools/<path>.tool.md` defaults Markdown tool name `<path>` when `name` is omitted
- `agents/<path>.agent.md` defaults Markdown agent name `<path>` when `name` is omitted
- `tool.<group>/` and `agent.<group>/` prepend `<group>.` to those derived Markdown names
- Python tool modules discovered in `tools/` or `tool.<group>/` still export the public tool names declared by the module itself

Markdown-backed assets participate in the same registries and precedence rules as direct resource folders and Python factories referenced from Markdown.

## Common Syntax

Most Markdown assets support three content layers:

1. YAML front matter for structured fields
2. fenced blocks for typed structured sections
3. Markdown body text for prompts or descriptions

### YAML front matter

Front matter must be a YAML mapping.

Example:

```md
---
name: review
flow: core.react
tools:
  - core.read_file
---
Review changes conservatively.
```

### Fenced blocks

The Markdown asset parser recognizes named fenced blocks such as:

- `yaml spec`
- `yaml flow`
- `yaml tool`
- `yaml agent`
- `yaml profile`
- `yaml config`
- `yaml schema`
- `mermaid`
- `mermaid graph`
- `dot`

Current behavior:

- YAML blocks whose label matches the asset type are deep-merged into front matter
- `yaml schema` is used by Markdown tools for the tool input schema
- `mermaid` and `dot` blocks are preserved as graph metadata for Markdown flows
- fenced `markdown`, `md`, and `text` blocks may contribute prompt or description text when the asset kind supports it

### Markdown body text

The meaning of the body depends on asset kind:

- prompts: the whole file is prompt text
- tools: description text when no explicit `description` field is set
- flows: prompt text merged into the flow prompt bundle
- agent profiles: `inline_prompt`
- skills: inline skill guidance text

## Includes And Prompt Imports

Markdown prompt expansion is handled by the shared prompt loader.

Supported directives:

- `{{ include:path/to/file.md }}`
- `{{ import:prompt:namespace.prompt_name }}`
- `{{ import:prompt:resource_root.pocketcode.review }}`

Current rules:

- includes are resolved relative to the source file first
- path-based fallback resolution then searches the active prompt fallback directories
- when a fallback prompt directory is passed, PocketCoder also checks that directory's parent so documented paths such as `prompts/review.md` resolve correctly from a resource root
- prompt imports resolve through the live prompt registry
- nested includes are allowed
- include cycles are rejected

Examples:

```md
{{ include:shared/reviewing.md }}
{{ import:prompt:core.system }}
{{ import:prompt:resource_root.pocketcode.review }}
```

## Prompt Assets

Prompt files are plain Markdown prompt sources. They can be:

- auto-registered from flat `<resource_root>/*.prompt.md`
- loaded indirectly as path-based prompt files from flows, agents, or skills

Prompt files support nested `include` and registry-backed `import` expansion.

Direct prompt registrations use canonical registry names such as:

- `core.system`
- `resource_root.pocketcode.review`
- `workspace.review` for the default `.pocketcode/` compatibility namespace

When a path-based prompt source is loaded, PocketCoder records the contributing source files so runtime prompt provenance remains visible on the compiled flow definition.

## Markdown Tool Assets

Markdown tool files describe tool metadata, but they do not replace Python execution.

The Markdown file provides:

- `name`
- `description`
- `handler`
- `schema`
- `execution_mode`
- `timeout_seconds`

The underlying executable implementation still comes from the required `handler` field.

For Python tool modules discovered by convention rather than through a Markdown wrapper, `*.tool.py` is the preferred filename shape. The runtime still accepts other `*.py` files in direct tool folders and skill tool folders for compatibility.

Current supported handler forms are:

- `path.py:ObjectName`
- `module.ObjectName`

Example:

````md
---
name: workspace_echo
handler: ./workspace_echo.py:WorkspaceEchoTool
description: Echo text back to the caller.
execution_mode: inline
---

```yaml schema
type: object
properties:
  text:
    type: string
required:
  - text
```
````

Current runtime behavior:

- the Markdown definition is compiled into metadata first
- the handler is resolved through the same loader used for manifest Python tool references
- the runtime wraps the loaded handler with the Markdown description, schema, execution mode, timeout, and source path metadata
- `tool_runtime` reports the Markdown source path when the tool came from a Markdown asset

Current validation behavior:

- tool authoring rejects missing handler files
- tool authoring rejects missing handler objects
- tool authoring rejects invalid import-path handlers
- Markdown `include` and `import` directives inside tool files are expanded and validated before reload

## Markdown Flow Assets

Markdown flows compile into ordinary `FlowDefinition` objects.

### Supported flow forms

1. **Python factory flow**: The Markdown file supplies `module` and `entry_fn`.
2. **StackVM flow**: The Markdown file includes fenced `vm` or `stackvm` blocks. **This is the recommended way to author flows.**

> [!TIP]
> **Use StackVM for all new flows.** It replaces the legacy graph-based flow system with a more powerful and flexible stack-based orchestration language.
> See [**StackVM Cookbook**](stackvm_cookbook.md) for patterns, [**StackVM Patterns**](stackvm_patterns.md) for architecture, and [**StackVM Macros**](stackvm_macros.md) for advanced usage.

Mermaid or DOT graph-authored Markdown flows are no longer a supported execution form in the current runtime. Existing graph definitions should be migrated to StackVM.

### Self-contained VM layout

The preferred executable Markdown shape is:

- front matter for structured config such as `tools`, `tool_files`, `prompt_files`, and handoff config
- Markdown body for the prompt text
- fenced `vm` blocks for the executable program

`tool_files` is optional. When present, each path is resolved relative to the Markdown file, loaded as a Python tool module, and registered into the same namespace before the flow is finalized. If `tool_files` is present and `tools` is omitted, the exported tool names become the flow's base tool list automatically. If `tool_files` is omitted, the loader also checks for a sibling `<name>.tool.py` file automatically.

Likewise, when a Markdown flow omits explicit prompt-file fields, the loader checks for a sibling `<name>.prompt.md` file and appends it to the resolved prompt bundle automatically.

Recommended helper layout:

```text
review.md
review.tool.py
prompts/shared.prompt.md
```

### Flow prompt behavior

Markdown flow prompt content can come from:

- inline body text
- `system_prompt` or `prompt`
- `system_prompt_file` or `prompt_file`
- `prompt_files`
- `prompts` as a compatibility alias
- `prompt:` resource references anywhere a prompt file reference is accepted

The loader resolves those through the shared prompt bundle path and stores the resulting `system_prompt` and `prompt_sources` on the compiled `FlowDefinition`.

## Markdown Agents

Markdown agents compile into the same `CompositeAgent` model used by YAML agent files.

Current supported front matter keys mirror the agent profile schema:

- `name`
- `flow`
- `extends` or `base_agent`
- `description`
- `llm_profile`
- `skills`
- `tools`
- `commands`
- `extra_prompts`
- `tool_confirmation`

Current body behavior:

- the Markdown body becomes `inline_prompt`
- `include` and `import` directives are expanded before profile creation

Current inheritance behavior:

- `extends` is normalized into `base_agent`
- `flow` may be omitted when `extends` is present
- omitted `llm_profile`, `skills`, and `tools` stay unset in the stored agent and inherit later at runtime
- `commands` are preserved as declarative agent-command alias metadata and merge by `name` during agent inheritance
- parent `inline_prompt` / `extra_prompts` are prepended to the child during effective-agent resolution

Current `commands` target forms are:

- plain string target such as `memory compact 1`
- structured target mapping such as:

```yaml
commands:
  - name: compact-via-review
    target:
      kind: agent_command
      agent: review.worker
      command: trim-delegated
      visibility: delegated
```

- local-handler target mapping such as:

```yaml
commands:
  - name: local-review
    target:
      kind: local_handler
      handler: review_local
```

Command entries may also declare descriptive schema/policy metadata:

```yaml
commands:
  - name: compact-now
    target: memory compact 1
    payload_schema:
      type: object
      properties:
        mode:
          type: string
    result_schema:
      type: object
      properties:
        summary:
          type: string
    policy:
      confirmation: confirm
```

Those fields are preserved by Markdown and YAML agent loading and are exposed through runtime command specs, but they are not yet enforced as hard schema-validation rules.

Current runtime enforcement updates:

- `payload_schema` is now validated when a command is invoked through the structured active-agent command runtime with a payload mapping
- `result_schema` is now validated against the structured `data` field returned by the command result
- the implemented validator currently supports `type`, `properties`, `required`, plus primitive property types such as `string`, `integer`, `number`, `boolean`, `object`, and `array`
- `policy` remains descriptive metadata for now

### Self-Contained Hybrid Agents

Markdown agent profiles can optionally include flow definition fields (like `vm_source`, `vm_entry`, or `module`) to create a self-contained hybrid agent. This allows logic and personality to coexist in a single file.

If any flow-related fields are detected in the front matter or fenced blocks, the system synthesizes a matching `FlowDefinition` and registers it automatically.

Example self-contained agent:

```md
---
name: echo-bot
execution_mode: vm
vm_entry: main
---
You are an echo bot.

```vm
[ request answer ] "main" define
```
```

Current load and save behavior:

- workspace profiles load from both legacy flat `<resource_root>/*.agent.yaml` or `<resource_root>/*.agent.md` files and grouped `agent.<group>/` collections
- new or cloned workspace agent profiles are written under `agent.<group>/...`, using the first name segment as the group directory
- saving a Markdown-backed workspace profile preserves Markdown format instead of rewriting to YAML
- cloning a Markdown-backed workspace profile preserves its Markdown naming convention, including `.agent.md`
- when a Markdown-backed agent has `base_agent`, save writes it back as `extends`

Current validation behavior:

- agent `flow` refs are normalized and validated against the live flow registry before reload for workspace Markdown edits and clones
- agent `extends` refs are normalized and validated against the currently loaded executable or authored agent names before reload
- explicit `tools` refs are validated against the live tool registry before reload
- `prompt:` entries in `extra_prompts` are validated against the live prompt registry before reload
- path-based `extra_prompts` are loaded and validated through the shared prompt loader before reload

## Markdown Skills

Skills are rooted at `<resource_root>/skills/<skill_name>/` and require `SKILL.md`.

The Markdown file contributes:

- skill metadata from front matter
- inline guidance from the body
- `tools` references to already-registered tools
- `extra_prompts`

Skill directories may also contain:

- `tools/*.tool.py` for preferred skill-local Python tools
- other `tools/*.py` files for compatibility
- `references/`
- `assets/`
- `scripts/`

Current load-time validation behavior:

- referenced `tools` must resolve against the live tool registry
- `prompt:` entries in `extra_prompts` must resolve against the prompt registry
- path-based prompt files in `extra_prompts` must load successfully from the skill root plus prompt fallback dirs

## Workspace Authoring And Editing

Workspace Markdown assets are managed through the shared engine asset API.

Current `/asset` support covers:

- `agent`
- `flow`
- `tool`

Current CLI operations are:

- create
- list
- show
- clone
- edit
- delete

Current Textual UI support covers:

- editing workspace Markdown flow and tool assets
- cloning workspace Markdown flow and tool assets
- deleting workspace Markdown flow and tool assets

Workspace Markdown asset editing and cloning validates the asset before reload so broken references fail during authoring rather than surfacing only during a later startup.

## Validation Timeline

Markdown assets currently validate at three different stages:

1. parse and compile time: front matter shape, YAML block shape, include and import expansion
2. load or authoring time: live-registry and file-path validation for the specific asset kind
3. narrow engine post-load normalization: contextual rebinding and canonicalization that still depend on the fully populated runtime state

This means:

- malformed Markdown assets are rejected while loading
- workspace Markdown edits and clones fail before reload when they point at missing handlers, prompts, tools, or flows
- skills are skipped before they become selectable when their static refs are invalid

## Canonical References

The most relevant implementation files are:

- `pocketcode/core/markdown_assets.py`
- `pocketcode/core/markdown_graph_flow.py`
- `pocketcode/core/prompt_loader.py`
- `pocketcode/core/workspace_catalog.py` for the canonical `WorkspaceCatalog` import surface
- `pocketcode/core/plugin_manager.py` as the current implementation module behind `WorkspaceCatalog`
- `pocketcode/core/agent_profile_manager.py`
- `pocketcode/core/markdown_profiles.py`
- `pocketcode/core/engine.py`
