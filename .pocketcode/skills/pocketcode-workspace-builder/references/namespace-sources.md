# Namespace Sources

Primary sources:
- `pocketcode/core/resource_roots.py`
- `pocketcode/core/workspace_catalog.py`
- `docs/architecture.md`
- `docs/configuration.md`

## Resource-root rules

`resource_roots.py` and `workspace_catalog.py` are the discovery truth:
- `.pocketcode/` is the default workspace resource root
- additional `.pocket*` roots are discovered by hint-based scanning
- `runtime.workspace_paths` adds plain namespace roots
- flat namespace-pack files and grouped collections both participate in the catalog

Valid top-level sections commonly used:
- `name`
- `description`
- `tools`
- `flows`
- `prompts`
- `llm_profiles`

## What the catalog actually registers

`WorkspaceCatalog`:
- discovers resource roots and configured namespace roots
- registers tools, flows, prompts, hooks, skills, and LLM profiles
- treats qualified ids as dotted `namespace.name`
- resolves local tool names within the owning namespace first
- normalizes legacy `namespace::tool` and `namespace::flow` references

Important behavior:
- prompt text is resolved during catalog load
- Python-backed flows load eagerly from the referenced module factory
- self-contained Markdown agents may synthesize embedded flow definitions
- flow metadata includes `namespace` and `namespace_root`
- flow defaults can synthesize or contribute namespace-provided authored agents

## Prompt handling inside namespaces

Prompt files are resolved by `resolve_prompt_bundle()`:
- inline prompt fields are concatenated first
- prompt files are loaded after that
- `prompts:` is accepted as an alias for `prompt_files` in flow definitions
- prompt includes use `{{ include:path.md }}`

## Authoring checklist

When creating or editing a namespace:
1. Start with the resource-root path and intended qualified id.
2. Register tools with adjacent `*.tool.py` or Markdown `*.tool.md` assets.
3. Register flows with `module` and `entry_fn` or with StackVM fields in Markdown.
4. Put prompt files inside the same resource root where possible.
5. Use qualified cross-namespace names when referencing non-local tools or flows.
6. Add a namespace-local `.agent.*` only when an authored agent is needed.

## Good local references

Prefer:
- `read_file` when the tool is owned by the same namespace
- `core::read_file` or `core.read_file` for cross-namespace use

Avoid:
- ambiguous bare names when multiple namespaces can own the same tool
- repo-only references in prompts or skill references when the workspace may not contain the repo
