# Namespace Authoring

Primary sources:
- `pocketcode/core/resource_roots.py`
- `pocketcode/core/workspace_catalog.py`
- `docs/architecture.md`
- `docs/configuration.md`
- `docs/pocketflow_agents.md`

## Canonical layout

Typical namespace-pack layout under a resource root:
```text
.pocketcode/
├── my_namespace.worker.md
├── my_namespace.system.prompt.md
├── my_namespace.tool_name.tool.py
└── my_namespace.agent_name.agent.md
```

Grouped collections are also supported when a resource root has multiple related assets:

```text
.pocketcode/
├── agent.review/safe.agent.md
├── tool.review/checklist.tool.py
├── prompts/review/base.md
└── skills/my_skill/SKILL.md
```

## Runtime truths

From `workspace_catalog.py`, `resource_roots.py`, and `agent_profile_manager.py`:
- resource roots are discovered from `.pocketcode/` and other `.pocket*` roots
- namespace-pack files are registered by qualified dotted ids such as `namespace.flow`
- self-contained `.agent.md` files can synthesize their own executable flow definitions
- local tool and prompt refs resolve within the owning namespace first
- legacy `namespace::name` references normalize to canonical dotted ids

Common executable asset fields:
- `description`
- `llm_profile`
- `tools`
- `prompt_files`
- `module`
- `entry_fn`
- `vm_entry`
- `vm_source`

## Editing rules

1. Prefer flat namespace-pack files for self-contained workspace assets.
2. Use grouped `agent.<group>/`, `tool.<group>/`, `prompts/`, and `skills/` directories when a namespace has multiple related assets.
3. Use local tool names for namespace-owned tools and qualified names for cross-namespace tools.
4. Keep prompts beside the owning asset unless they are intentionally shared.
5. Add `.agent.*` files only when an authored agent overlay or self-contained agent is needed.

## Good local references

Prefer:
- `read_file` when the tool is owned by the same namespace
- `core::read_file` or `core.read_file` for cross-namespace use

Avoid:
- ambiguous bare names when multiple namespaces can own the same tool
- repo-only references in prompts or skill references when the workspace may not contain the repo
