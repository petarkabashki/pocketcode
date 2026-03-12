---
name: pocketcode-plugin-authoring
description: Use when creating or editing PocketCoder plugins under .pocketcode/. Covers plugin.yaml, flow registration, prompts, plugin-local tools, plugin-local agents, qualified names, and plugin discovery behavior.
tools:
  - core.read_file
  - core.list_files
  - core.search_code
---
Use this skill for plugin-scoped authoring.

Read first:
- `references/plugin-authoring.md`

Apply it when the task touches:
- `.pocketcode/<plugin>/plugin.yaml`
- `.pocketcode/<plugin>/*.py`
- `.pocketcode/<plugin>/*.prompt.md`
- `.pocketcode/<plugin>/*.tool.py`
- `.pocketcode/<plugin>/*.agent.yaml`

Prefer local plugin ownership when the resource is specific to one plugin. Promote to workspace scope only when the asset is intentionally shared across plugins.

