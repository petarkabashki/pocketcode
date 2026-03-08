# Modes And Skills

This document describes the current Markdown-authored runtime overlay system.

See `markdown_assets.md` for the shared Markdown syntax, include and import behavior, and asset-validation model used by modes and skills.

## Overview

Modes and skills are session-time overlays on top of the flow plus agent-profile runtime.

- a mode resolves into one ephemeral active profile
- skills are additive and can be enabled together

Neither introduces a second execution engine.

## Modes

### Location

Modes are loaded from every discovered resource root under:

```text
<resource_root>/modes/*.md
```

### File Format

Modes use YAML front matter plus a Markdown body.

Example:

```md
---
name: review
description: Review mode
flow: core.react
llm_profile: fast-review
tool_confirmation:
  default: confirm
---
Focus on bugs, regressions, unsafe assumptions, and missing tests.
```

### Supported Front Matter Keys

- `name`
- `description`
- `flow`
- `agent`
- `llm_profile`
- `tools`
- `extra_prompts`
- `tool_confirmation`

### Tool Selection Semantics

Mode tool selection is normalized from front matter as follows:

- omitted: inherit from the base profile
- `all` or `*`: unrestricted profile tool filter
- `none` or `deny`: empty allowlist
- `inherit` or `default`: clear explicit mode tool override
- list: explicit allowlist

### Mode Resolution

When a mode is activated, the engine resolves a base profile in this order:

1. `mode.agent`
2. `mode.flow`
3. current active profile
4. current flow default profile

Then it merges:

- target flow
- LLM override
- inline prompt body
- extra prompt files
- tool allowlist
- tool confirmation policy

The resulting object becomes the active ephemeral profile for the session.

### Mode Commands

Current commands:

```text
/mode list
/mode show [mode_name]
/mode switch <mode_name>
/mode clear
```

## Skills

### Location

Skills are loaded from every discovered resource root under:

```text
<resource_root>/skills/<skill_name>/
```

### Expected Layout

```text
.pocketcode/skills/python-testing/
├── SKILL.md
├── assets/
├── references/
├── scripts/
└── tools/
```

Only `SKILL.md` is required.

### `SKILL.md` Format

Example:

```md
---
name: python-testing
description: Pytest test loop
tools:
  - core.read_file
extra_prompts:
  - references/style.md
---
Reproduce failures first, then patch minimally.
```

### Skill Contributions

Skills can contribute:

- inline prompt body text
- referenced prompts through `extra_prompts`; entries may be file paths or `prompt:` resource references
- references to already-registered tools through `tools`
- new Python tool modules loaded from `tools/*.py`
- static reference files, scripts, and assets for human use

`SKILL.md` uses the same shared Markdown asset rules as other Markdown-backed resources: YAML front matter for structured keys, Markdown body text for inline guidance, and prompt expansion for `include` and `import` directives in prompt-bearing sections.

### Skill Tool Names

Skill-provided tools are registered under:

```text
skill.<slug>.<tool_name>
```

Where `<slug>` is derived from the skill name.

### Skill Commands

Current commands:

```text
/skill list
/skill show <skill_name>
/skill enable <skill_name>
/skill disable <skill_name>
```

`/skill list` groups skills by top-level name prefix.

## Discovery Controls

Modes and skills can be disabled without deleting them.

### `.disabled`

If any path component contains `.disabled`, the runtime skips that file or directory.

### `<resource_root>/.pocketcodeignore`

Direct modes and skills inside a resource root use rules from:

```text
<resource_root>/.pocketcodeignore
```

Patterns are gitignore-style and support `!` re-includes.

## Textual UI Integration

The Textual UI currently supports:

- switching the active mode
- enabling and disabling skills
- persisting last-used skill selections
- persisting per-profile skill selections for the active agent profile
- saving the current inspector skill selection into the active workspace agent profile file
- saving default skill selections to config
- saving full runtime selection presets that include mode and skills

When an active agent profile is selected, inspector toggles and the Control Center skill picker save the selected skills under that profile's Textual state. The inspector `Save` button writes the current selection into that profile's persisted `skills` field. If no profile-specific override exists, the runtime falls back to the profile file's `skills`, then the global last-used skill list, and finally `default_skills`.

The primary controls are exposed through:

- `F3` edit picker
- `F4` clone picker
- `F6` Control Center

## Prompt And Tool Precedence

Current runtime precedence for these overlays is:

```text
flow base -> active agent profile -> active mode -> enabled skills -> session overrides
```

More precisely:

- modes resolve into the active profile before a turn starts
- skills append prompt guidance and add tools after the profile has been resolved
- session-level Textual overrides can further modify profile tools and confirmation overrides

For modes, skills, and agent overlays, `extra_prompts` now accepts either:

- a path such as `prompts/review.md`
- a prompt resource reference such as `prompt:resource_root.pocketcode.review`

Malformed typed refs in mode and skill front matter are rejected while those files load. A bad `tool:` or `prompt:` value causes the specific mode or skill to be skipped with a warning instead of remaining partially loadable.

When the engine constructs the mode and skill managers, it also passes the live flow, tool, and prompt registries into them. That means validation happens during the normal mode or skill load itself, not in a later cleanup pass:

- modes are skipped if their `flow` reference cannot be resolved against the loaded flow or agent registry
- modes are skipped if their `agent` reference cannot be resolved against the loaded agent-profile registry
- modes and skills are skipped if any referenced `tools` entry cannot be resolved against the live tool registry
- modes and skills are skipped if any `prompt:` reference in `extra_prompts` cannot be resolved against the prompt registry
- modes and skills are skipped if any relative prompt file in `extra_prompts` cannot be loaded from the current resource-root prompt search path
- successfully loaded tool refs are stored in canonical dotted form such as `core.read_file`

Unqualified refs that depend on later per-turn context are still deferred until that context exists, but static mode and skill asset references are now rejected before those overlays become selectable.

## Repository-Shipped Workspace Skills

This repository currently ships workspace skills under `.pocketcode/skills/`, including:

- `pocketcode-workspace-builder`
- `pocketcode-graph-authoring`
- `pocketcode-plugin-authoring`
- `pocketcode-profiles-prompts`
- `pocketcode-tools-runtime`
- `pocketcode-workspace-assets`

These are ordinary workspace skills and follow the same loading rules as any other skill.
