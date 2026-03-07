# Profiles And Prompts

Primary sources:
- `pocketcode/core/runtime_models.py`
- `pocketcode/core/agent_profile_manager.py`
- `pocketcode/core/markdown_profiles.py`
- `pocketcode/core/prompt_loader.py`
- `docs/modes_and_skills.md`

## Composite agents

Composite agents can come from:
- flow-level `default_agent`
- plugin-local `agents/*.yaml`
- workspace `.pocketcode/agents/*.yaml`
- synthesized defaults

Fields to preserve:
- `name`
- `flow`
- `description`
- `llm_profile`
- `tools`
- `extra_prompts`
- `tool_confirmation`

## Modes and skills

From `markdown_profiles.py`:
- modes are markdown files with YAML front matter
- skills are directories with `SKILL.md`
- skill front matter only needs lightweight metadata; detailed instructions belong in the body or `references/`

## Prompt include behavior

From `prompt_loader.py`:
- includes are recursive
- relative paths resolve from the current prompt file
- caller-provided fallback dirs are optional
- cycles raise an error

## Editing rules

1. Put the primary prompt close to the owning asset.
2. Use `extra_prompts` for overlays, not for the main asset prompt.
3. Avoid repo-only prompt includes when the asset should be portable across workspaces.
4. Keep confirmation policies and tool lists minimal and explicit.

