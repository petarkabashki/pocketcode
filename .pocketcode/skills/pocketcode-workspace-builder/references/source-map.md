# Source Map

Use this file to choose the right reference set before editing.

## PocketFlow graph mechanics

Read:
- `pocketflow.py`
- `pocketflow.md`
- `docs/pocketflow_agents.md`
- `references/pocketflow-sources.md`

Use for:
- creating or editing `Node`, `Flow`, `BatchNode`, `AsyncNode`, `AsyncFlow`
- transition wiring with `>>` and action-labelled edges
- retry behavior, shared store access, async/batch patterns

## Plugin manifests and flow registration

Read:
- `pocketcode/core/manifest_loader.py`
- `pocketcode/core/plugin_manager.py`
- `docs/plugin_architecture.md`
- `specs/003-unified-plugin-namespace/quickstart.md`
- `references/plugin-sources.md`

Use for:
- `plugin.yaml`
- `flows:` blocks
- prompt registration and prompt file resolution
- plugin discovery, qualified names, and cross-plugin references

## Composite agents, prompts, modes, and skills

Read:
- `pocketcode/core/runtime_models.py`
- `pocketcode/core/agent_profile_manager.py`
- `pocketcode/core/markdown_profiles.py`
- `pocketcode/core/prompt_loader.py`
- `docs/modes_and_skills.md`
- `references/profile-and-prompt-sources.md`

Use for:
- `agents/*.yaml`
- `.pocketcode/agents/*.yaml`
- prompt includes and fallback resolution
- mode and skill front matter
- tool confirmation and LLM profile overlays

## Tool authoring and runtime execution

Read:
- `pocketcode/core/interfaces.py`
- `pocketcode/core/tool_runtime.py`
- `pocketcode/core/agent_runtime.py`
- `references/tool-and-runtime-sources.md`

Use for:
- `BaseTool` implementations
- callable workspace tools
- managed subprocess tools
- allowlists, confirmation policies, and active skill tools

## Workspace assets and portability

Read:
- `readme.md`
- `docs/modes_and_skills.md`
- `.pocketcode/plugins/workspace_builder/prompts/authoring_reference.md`
- `references/workspace-assets.md`

Use for:
- `.pocketcode/plugins/`
- `.pocketcode/tools/`
- `.pocketcode/prompts/`
- `.pocketcode/skills/`
- `.pocketcode/agents/`
- portability when the current workspace is not the repo root

