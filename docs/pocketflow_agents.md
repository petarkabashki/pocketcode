# Flows And Agent Profiles

This document describes the current relationship between executable flows and agent profiles.

## One Executable Model, Multiple Overlays

PocketCoder executes flows. Agent profiles do not replace flows; they configure how a selected flow runs.

The current stack is:

1. flow definition
2. agent profile
3. optional active mode
4. optional enabled skills
5. session overrides from the CLI or Textual UI

## Flow Authoring With PocketFlow

The canonical authored flow path is:

1. implement a PocketFlow factory in Python
2. register it in `plugin.yaml` under `flows:`

Example:

```python
from pocketflow import Flow, Node


class ThinkNode(Node):
    def prep(self, shared):
        return shared.get("task", "")

    def exec(self, task):
        return task

    def post(self, shared, prep_res, exec_res):
        shared["result"] = exec_res
        return "done"


def create_flow() -> Flow:
    return Flow(start=ThinkNode())
```

Manifest registration:

```yaml
flows:
  analyst:
    module: flows/analyst.py
    entry_fn: create_flow
    description: Analyze the current workspace.
```

## What A Flow Definition Can Do

A flow definition can supply:

- a PocketFlow `flow_instance`
- an `llm_profile`
- a base tool list
- handoff targets and policies
- pre, step, and post handlers
- base prompt text and prompt source files
- an inline default agent profile

The flow is the authoritative base layer for execution.

## Agent Profiles

An agent profile is a named `CompositeAgent` that targets one flow.

Profiles can change:

- `llm_profile`
- `inline_prompt`
- `extra_prompts`
- `skills`
- `tools`
- `tool_confirmation`

Profiles do not define executable graph logic. They select and constrain behavior for an existing flow.

## Agent Profile Sources

Current profile sources are:

1. inline `default_agent` inside a flow definition
2. plugin-local `agents/*.yaml`
3. workspace `.pocketcode/agents/*.yaml`
4. synthesised fallback profile created from the flow definition

Effective precedence is:

1. plugin-defined profiles
2. workspace profiles
3. synthesised defaults

## Synthesised Defaults

Every loaded flow gets a synthesised default profile if no higher-precedence profile replaces that name.

That synthesised profile:

- uses the flow's qualified name as its own name
- targets the same flow
- inherits the flow's `llm_profile`
- inherits the flow's tool list

## Workspace Agent Profile Schema

Current workspace profile schema:

```yaml
name: my-review-profile
flow: core.react
description: Review-focused profile
llm_profile: fast-review
skills:
  - python-testing
tools:
  - core.read_file
  - core.search_code
extra_prompts:
  - prompts/review.md
tool_confirmation:
  default: confirm
  overrides:
    core.execute_command: deny
```

Notes:

- `flow` is required.
- `skills` omitted means fall back to the global Textual skill defaults for that session.
- `tools` omitted means inherit the flow tool surface.
- `tools: []` means allow no base tools.

## Modes Resolve Into Profiles

Modes are not a separate execution system. A mode is resolved into an ephemeral agent profile.

Mode resolution in the engine works like this:

1. resolve a base profile from `mode.agent`, `mode.flow`, the active profile, or the current flow
2. merge mode `llm_profile`, prompts, tools, and confirmation policy
3. activate the resulting ephemeral profile against the target flow

Mode inline prompt text is appended after the base profile inline prompt.

## Skills Extend The Active Profile

Skills do not replace the active profile either. They extend it by adding:

- inline prompt guidance
- extra prompt files
- references to existing tools
- skill-provided tool modules

Skill prompt text is appended after the active profile prompt content.

## Effective Prompt Composition

For a given flow turn, the effective prompt is:

1. flow system prompt
2. active profile inline prompt
3. active profile extra prompt files
4. enabled skill inline prompts
5. enabled skill extra prompt files

## Effective Tool Surface

For a given flow turn, the effective tool surface is:

1. flow tools
2. filtered by active profile allowlist when present
3. extended by enabled skill references to existing tools
4. extended by enabled skill-provided tools

## Programmatic Flow Runtime Helpers

When a PocketFlow `flow_instance` runs, the runtime injects services into the shared store, including:

- `_llm_router`
- `_tool_runtime`
- `_agent_llm_profile`
- `_agent_system_prompt`
- `_agent_tool_definitions`
- `_registry`

These are runtime conveniences, not part of the manifest schema.

## Handoffs

A flow can hand off to other flows through `handoff_agents` and optional handoff policy configuration.

Current handoff behavior supports:

- target flow selection
- handoff-level LLM overrides
- whole-context or delegated-context mode
- optional return-to-caller behavior

## Authoring Guidance

When documenting or implementing new behavior, keep these distinctions explicit:

- flows are executable
- agent profiles are named overlays for flows
- modes are ephemeral overlays resolved into profiles
- skills are additive session extensions

That separation is the current canonical model in the codebase.
