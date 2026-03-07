---
name: pocketcode-workspace-builder
description: Use when creating or editing PocketCoder workspace resources, especially through the workspace_builder agent. Covers PocketFlow flows, plugin manifests, prompts, agents, tools, skills, modes, and workspace assets under .pocketcode/. This is the umbrella skill when a request spans multiple PocketCoder subsystems or needs a self-contained workspace-builder guide.
tools:
  - core.read_file
  - core.list_files
  - core.glob_files
  - core.search_code
---
Use this as the entry skill for the `workspace_builder` agent.

Workflow:
1. Identify the asset type first: PocketFlow graph, plugin, prompt/profile, tool/runtime behavior, or workspace-level asset.
2. Read [references/source-map.md](references/source-map.md) to map the task to the real implementation files.
3. For the concrete subsystem, read one or more focused references:
   - `references/pocketflow-sources.md`
   - `references/plugin-sources.md`
   - `references/profile-and-prompt-sources.md`
   - `references/tool-and-runtime-sources.md`
   - `references/workspace-assets.md`
4. Prefer the implementation files over high-level docs when they disagree.
5. Keep changes minimal, update docs with code changes, and verify with the smallest relevant tests.

Working rules:
- Treat `pocketflow.py` as the execution truth for graph semantics.
- Treat `pocketflow.md` and `docs/*.md` as authoring guides, not runtime truth.
- Treat `pocketcode/core/*.py`, plugin manifests, and tests as the source of truth for PocketCoder behavior.
- Do not assume the active workspace contains the whole repo; inspect what is actually present before reusing repo-local paths.

