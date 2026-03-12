---
name: pocketcode-profiles-prompts
description: Use when creating or editing PocketCoder composite agents, workspace agent profiles, modes, skills, prompt files, prompt includes, and LLM/tool confirmation overlays. Covers precedence rules and prompt resolution behavior.
tools:
  - core.read_file
  - core.search_code
---
Use this skill for profile and prompt work.

Read first:
- `references/profiles-prompts.md`

Use it when the task touches:
- `agents/*.yaml`
- `.pocketcode/*.agent.yaml`
- `.pocketcode/modes/*.md`
- `.pocketcode/skills/*/SKILL.md`
- prompt files and `{{ include:... }}` chains

Keep the precedence model intact: flow defaults first, then composite agents, then mode/skill/session overlays.

