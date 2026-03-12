# Tools And Runtime

Primary sources:
- `pocketcode/core/interfaces.py`
- `pocketcode/core/tool_runtime.py`
- `pocketcode/core/agent_runtime.py`
- `pocketcode/core/markdown_profiles.py`

## Supported tool shapes

PocketCoder executes:
- `BaseTool` subclasses
- `BaseTool` instances
- public callables

`BaseTool` is the right choice when you need:
- explicit `schema`
- `execution_mode`
- subprocess support
- stable tool metadata

## Runtime enforcement

`ToolRuntime.execute_tool()` enforces:
- active allowlists from the shared store
- active profile restrictions
- confirmation policy resolution
- inline or managed subprocess execution

## Skill and workspace tool loading

`markdown_profiles.py` loads skill-owned tools from `tools/*.py`.
Workspace tools are loaded separately from `.pocketcode/*.tool.py or .pocketcode/*.tool.md` by the plugin/runtime stack.

## Editing rules

1. Keep schemas small and concrete.
2. Decide early whether the tool is plugin-local, workspace-shared, or skill-local.
3. Use managed subprocess only when in-process execution is unsuitable.
4. Test the runtime path that will actually execute the tool.

