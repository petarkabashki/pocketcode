# Workspace Assets

Primary sources:
- `readme.md`
- `docs/modes_and_skills.md`
- `pocketcode/core/markdown_profiles.py`
- `.pocketcode/workspace_builder.authoring_reference.prompt.md`

## Scope rules

Use workspace scope for assets that are meant to be reused broadly:
- shared tools
- shared prompts
- reusable skills
- reusable modes
- workspace agent profiles

Use plugin scope for assets that belong to one plugin's behavior.

## Portability rules

When the current workspace is not this repo:
- only files in that workspace are guaranteed
- repo-local docs or source files may be absent
- skills and prompts should carry enough local guidance to be maintainable on their own

## Editing rules

1. Keep the conventional `.pocketcode/` layout intact.
2. Use relative references within the workspace.
3. Avoid hidden dependencies on repo-only files.
4. Update local guidance when behavior changes.

