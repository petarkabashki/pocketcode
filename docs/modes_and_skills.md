# Skills And Legacy Modes

This document describes the current skill system.

See [`markdown_assets.md`](markdown_assets.md) for shared Markdown syntax and [`agent_system.md`](agent_system.md) for how skills interact with agent profiles.

## Current Model

Skills are the only remaining session-time overlay surface.

- flows stay executable units
- agent profiles provide persistent named configuration
- skills add prompt guidance and tools at session time

Legacy session modes have been removed from the engine, CLI, Textual UI, saved-session model, and workspace Markdown loaders.

If an older workspace still contains `.pocketcode/modes/*.md`, those files are ignored by current builds and should be migrated into named agent profiles or skill guidance.

## Skill Layout

Skills are discovered from every resource root under:

```text
<resource_root>/skills/<skill_name>/
```

Expected layout:

```text
.pocketcode/skills/python-testing/
├── SKILL.md
├── assets/
├── references/
├── scripts/
└── tools/
```

Only `SKILL.md` is required.

## `SKILL.md`

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

Skills can contribute:

- inline prompt body text
- prompt sources from `extra_prompts`
- references to existing tools through `tools`
- new Python tools from `tools/*.tool.py`
- human-facing references, scripts, and assets

Skill-provided tools are registered under:

```text
skill.<slug>.<tool_name>
```

## Runtime Behavior

Skills are additive and can be enabled together. They do not replace the active profile or flow.

Prompt precedence is:

```text
flow base -> active agent profile -> enabled skills -> session overrides
```

Skill validation happens during load:

- `tools` entries must resolve against the live tool registry
- `prompt:` entries in `extra_prompts` must resolve against the prompt registry
- relative prompt files in `extra_prompts` must load from the skill root or prompt fallback dirs

Invalid skills are skipped rather than partially loaded.

## Commands And UI

CLI commands:

```text
/skill list
/skill show <skill_name>
/skill enable <skill_name>
/skill disable <skill_name>
```

Textual UI support includes:

- enabling and disabling skills
- persisting last-used skill selections
- persisting per-profile skill selections
- saving the current skill selection into the active workspace agent profile
- saving default skill selections to config
- saving selection presets that include profile, LLM, skill, and confirmation state

## Discovery Controls

Skills are skipped when:

- any path component contains `.disabled`
- the resource root's `.pocketcodeignore` excludes the file or directory

## Migration From Modes

Use these replacements for older mode-based workflows:

- persistent behavior difference: create an agent profile
- additive temporary guidance or tools: create a skill
- session-specific tool/confirmation choice: use existing session overrides

The repository may still contain historical references to "modes" in older specs or generic phrases such as "execution mode". Those are not the removed session mode feature.
