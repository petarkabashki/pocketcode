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

## Namespace assets and flow registration

Read:
- `pocketcode/core/resource_roots.py`
- `pocketcode/core/workspace_catalog.py`
- `docs/architecture.md`
- `docs/configuration.md`
- `references/namespace-sources.md`

Use for:
- flat namespace-pack flow assets
- grouped resource-root collections
- prompt registration and prompt file resolution
- resource-root discovery, qualified names, and cross-namespace references

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
- `.pocketcode/*.agent.yaml`
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
- `.pocketcode/workspace_builder.authoring_reference.prompt.md`
- `references/workspace-assets.md`

Use for:
- `.pocketcode/`
- `.pocketcode/*.tool.py or .pocketcode/*.tool.md`
- `.pocketcode/*.prompt.md`
- `.pocketcode/skills/`
- `.pocketcode/*.agent.*`
- portability when the current workspace is not the repo root
