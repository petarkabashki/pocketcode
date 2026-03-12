# Profile And Prompt Sources

Primary sources:
- `pocketcode/core/runtime_models.py`
- `pocketcode/core/agent_profile_manager.py`
- `pocketcode/core/markdown_profiles.py`
- `pocketcode/core/prompt_loader.py`
- `docs/modes_and_skills.md`
- `docs/pocketflow_agents.md`

## Composite agent model

`runtime_models.py` defines the composite agent fields:
- `name`
- `flow`
- `description`
- `llm_profile`
- `inline_prompt`
- `extra_prompts`
- `tools`
- `tool_confirmation`
- `source`
- `source_path`

`FlowDefinition.default_agent_profile` holds the flow's default composite agent.

## Agent profile precedence

`agent_profile_manager.py` loads agents in this order:
1. plugin-declared default agent
2. plugin-local `agents/*.yaml`
3. workspace `.pocketcode/*.agent.yaml`
4. synthesized default profile from the flow definition

Collision precedence is:
- plugin
- workspace
- synthesized

## Workspace modes and skills

`markdown_profiles.py` defines:
- modes in `.pocketcode/modes/*.md`
- skills in `.pocketcode/skills/<name>/SKILL.md`

Mode front matter can set:
- `name`
- `description`
- `flow`
- `agent`
- `llm_profile`
- `tools`
- `extra_prompts`
- `tool_confirmation`

Skill front matter can set:
- `name`
- `description`
- `tools`
- `extra_prompts`

Skill directories can also provide:
- `tools/`
- `scripts/`
- `references/`
- `assets/`

## Prompt resolution

`prompt_loader.py` is the source of truth:
- includes use `{{ include:path.md }}`
- relative include paths are resolved from the current prompt file
- fallback directories are only used when provided by the caller
- cycles raise an error
- prompt sources are deduplicated

## Authoring checklist

When editing profiles or prompts:
1. Decide whether the change belongs in the flow definition, a plugin-local agent YAML, a workspace agent YAML, a mode, or a skill.
2. Keep prompt files local to the asset when possible.
3. Use `extra_prompts` for reusable overlays, not for the asset's primary prompt.
4. Keep `tool_confirmation` precise; avoid broad overrides unless necessary.
5. If the workspace may be portable, avoid prompt includes that depend on repo-only paths.

