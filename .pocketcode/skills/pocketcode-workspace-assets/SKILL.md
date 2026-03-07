---
name: pocketcode-workspace-assets
description: Use when creating or editing workspace-level PocketCoder assets under .pocketcode/, including shared tools, prompts, skills, modes, workspace agent profiles, and portability rules for non-repo workspaces.
tools:
  - core.read_file
  - core.list_files
  - core.glob_files
---
Use this skill for workspace-scoped assets that are not owned by a single plugin.

Read first:
- `references/workspace-assets.md`

Choose workspace scope when the asset is intentionally shared across plugins or sessions:
- `.pocketcode/tools/`
- `.pocketcode/prompts/`
- `.pocketcode/skills/`
- `.pocketcode/modes/`
- `.pocketcode/agents/`

Prefer plugin scope when the asset is specific to one plugin.

