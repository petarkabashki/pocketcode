---
name: pocketcode-plugin-authoring
description: Use when creating or editing PocketCoder plugins under .pocketcode/plugins/. Covers plugin.yaml, flow registration, prompts, plugin-local tools, plugin-local agents, qualified names, and plugin discovery behavior.
tools:
  - core.read_file
  - core.list_files
  - core.search_code
---
Use this skill for plugin-scoped authoring.

Read first:
- `references/plugin-authoring.md`

Apply it when the task touches:
- `.pocketcode/plugins/<plugin>/plugin.yaml`
- `.pocketcode/plugins/<plugin>/flows/*.py`
- `.pocketcode/plugins/<plugin>/prompts/**/*.md`
- `.pocketcode/plugins/<plugin>/tools/*.py`
- `.pocketcode/plugins/<plugin>/agents/*.yaml`

Prefer local plugin ownership when the resource is specific to one plugin. Promote to workspace scope only when the asset is intentionally shared across plugins.

