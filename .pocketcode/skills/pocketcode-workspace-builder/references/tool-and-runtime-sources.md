# Tool And Runtime Sources

Primary sources:
- `pocketcode/core/interfaces.py`
- `pocketcode/core/tool_runtime.py`
- `pocketcode/core/agent_runtime.py`
- `pocketcode/core/markdown_profiles.py`

## Tool implementation shapes

From `interfaces.py`, a `BaseTool` should define:
- `name`
- `description`
- `schema`
- `execute(**kwargs)`

Optional runtime hooks:
- `execution_mode`
- `timeout_seconds`
- `spawn_subprocess()`
- `handle_subprocess_result()`

PocketCoder also accepts callable tools:
- docstring becomes the description
- signature is converted into a schema
- `shared_store` is injected when supported

## How ToolRuntime behaves

`tool_runtime.py` enforces:
- active per-turn allowlists from `shared_store["active_allowed_tools"]`
- fallback checks from the active agent profile
- confirmation policies with `allow`, `confirm`, and `deny`
- inline execution or managed subprocess execution

Managed subprocess tools are only valid for `BaseTool` implementations.

## How AgentRuntime prepares tools

`agent_runtime.py`:
- injects `_llm_router`, `_tool_runtime`, and `_registry` into the shared store
- computes effective tool names for the active agent each turn
- uses the agent/flow configuration plus active profile and skills to resolve the tool surface
- handles transitions such as `call_tool`, `handoff`, `final_answer`, and `ask_user`

## Skill tools

`markdown_profiles.py` loads skill-owned tools from `.pocketcode/skills/<skill>/tools/*.tool.py`:
- tools are auto-registered under `skill.<skill_slug>.<tool_name>`
- public callables and `BaseTool` implementations are both valid
- a `TOOLS` export can override discovery

## Authoring checklist

When building tools:
1. Use `BaseTool` when you need explicit schema or subprocess hooks.
2. Use callables for simple workspace or skill-local helpers.
3. Keep schemas concrete and minimal.
4. Check whether the tool must survive confirmation, allowlist, or skill scoping.
5. Add or update tests around the runtime path that will actually execute the tool.
