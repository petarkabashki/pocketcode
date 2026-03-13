---
name: pocketcode-namespace-authoring
description: Use when creating or editing PocketCoder namespace assets under .pocketcode/. Covers flat namespace-pack assets, resource-root discovery, qualified names, namespace-local tools, and self-contained agents.
tools:
  - core.read_file
  - core.list_files
  - core.search_code
---
Use this skill for namespace-scoped authoring.

Read first:
- `references/namespace-authoring.md`

Apply it when the task touches:
- flat `.pocketcode/<namespace>.<asset>.md` namespace-pack files
- flat `.pocketcode/<namespace>.*.tool.py` and `.tool.md` files
- flat `.pocketcode/<namespace>.*.prompt.md` files
- flat `.pocketcode/<namespace>.*.agent.md` and `.agent.yaml` files
- namespace roots configured through `runtime.workspace_paths`

Prefer local namespace ownership when the resource is specific to one namespace. Promote to shared workspace scope only when the asset is intentionally reused across namespaces.
