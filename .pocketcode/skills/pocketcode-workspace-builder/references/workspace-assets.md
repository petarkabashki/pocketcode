# Workspace Assets

Primary sources:
- `readme.md`
- `docs/modes_and_skills.md`
- `.pocketcode/workspace_builder.authoring_reference.prompt.md`
- `pocketcode/core/markdown_profiles.py`
- `pocketcode/core/discovery_rules.py`

## Workspace-owned locations

Use these locations deliberately:
- `.pocketcode/ flat namespace-pack files with the `<plugin>.` prefix` for plugin-scoped manifests, flows, prompts, tools, and plugin-local agent YAML
- `.pocketcode/*.agent.*` for workspace agent profiles
- `.pocketcode/*.prompt.md` for shared prompt files
- `.pocketcode/*.tool.py or .pocketcode/*.tool.md` for shared workspace tools
- `.pocketcode/skills/<skill>/` for workspace skills
- `.pocketcode/modes/` for workspace modes

## Discovery behavior

Assets can be skipped by:
- renaming any path component to contain `.disabled`
- ignore rules in `.pocketcode/.pocketcodeignore`

Skill and mode discovery is implemented by `markdown_profiles.py`.
Plugin and workspace resource discovery is implemented by `plugin_manager.py` and `discovery_rules.py`.

## Portability rules

If PocketCoder is run from another workspace:
- only paths inside that workspace are guaranteed to exist
- repo-local implementation files may not be present
- prompts, skills, and manifests should avoid hard-coded references to this repo unless the repo is the active workspace

To keep a workspace self-contained:
1. place instructions beside the asset that needs them
2. prefer relative references within `.pocketcode/`
3. avoid includes that depend on package source files
4. keep enough local documentation for the asset to be maintainable without the repo

## Authoring checklist

When editing workspace-level assets:
1. confirm the asset belongs at workspace scope, not plugin scope
2. keep the directory layout conventional so discovery keeps working
3. update any nearby docs or reference prompts that explain the asset
4. verify discovery with the smallest relevant test or load path

