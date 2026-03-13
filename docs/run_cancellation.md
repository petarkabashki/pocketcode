# Run Cancellation And Hard-Stop Design

This document is the canonical reference for the current cancellation model in PocketCoder and the currently implemented hard-stop behavior for long-running tools.

## Current State

PocketCoder currently supports cooperative run cancellation from the CLI and Textual UI:

- `/stop` and `/cancel` request cancellation on the active `RunHandle`
- the basic CLI also converts `Ctrl+C` during an active run into a stop request
- `AgentRuntime`, `WorkflowRuntime`, and runtime node boundaries check for cancellation and abort cleanly when control returns to the runtime

This works well for:

- agent-to-agent handoffs
- workflow/node transitions
- Python handlers between steps
- tool execution once the tool call returns
- user-input waits

This does **not** force-stop code that is currently blocked inside:

- an LLM provider call
- a Python tool function running inline in-process
- a blocking OS command launched inside a tool that does not expose its child process to the runtime

PocketCoder also has an implemented hard-stop path for managed subprocess tools such as `execute_command`. That path allows the runtime to terminate the underlying OS process when cancellation is requested.

## Constraint

The existing tool model is intentionally flexible:

- a tool can be a `BaseTool` subclass, a `BaseTool` instance, or a plain callable
- a callable may request `shared_store`
- some tools depend on live in-process objects such as `interaction_handler`, runtime event callbacks, and active agent profile state

Because of that, a blanket "run every tool in a subprocess" change would be unsafe. It would break tools that depend on non-serializable runtime state and would make behavior differ between tool types.

## Goals

1. Preserve the current cooperative cancellation behavior.
2. Add a hard-stop path for eligible long-running tools.
3. Keep interactive/shared-state tools in-process.
4. Make the isolation boundary explicit and opt-in.
5. Avoid changing the public behavior of existing tools unless they opt into the stronger execution mode.

## Non-Goals

- Force-killing arbitrary Python code running inline in the main process.
- Automatically subprocess-wrapping every registered tool.
- Solving provider-side cancellation for third-party LLM SDK calls that do not expose cancellable requests.

## Recommended Execution Model

Introduce per-tool execution modes with explicit eligibility.

### Mode 1: `inline`

Default mode. Current behavior.

Use for:

- tools that require `shared_store`
- tools that ask the user for input
- tools that rely on runtime callbacks or in-memory objects
- simple fast tools where hard-stop is unnecessary

Cancellation behavior:

- cooperative only
- cancellation is observed before the tool starts and after it returns

### Mode 2: `subprocess_json`

Opt-in mode for tools that can run in a separate process with JSON-serializable inputs and outputs.

Use for:

- search tools
- file-system tools
- shell/command tools
- deterministic compute tasks with no dependency on live runtime objects

Requirements:

- no `shared_store` parameter
- arguments must be JSON-serializable
- result must be JSON-serializable
- tool implementation must be importable by module path

Cancellation behavior:

- `ToolRuntime` owns the child process handle
- `/stop` can terminate the child process directly
- the runtime converts termination into a structured tool failure or cancellation event

### Implemented Phase 1: `managed_subprocess`

Current implementation for `execute_command`.

Use for:

- tools that already map naturally to a single OS child process
- tools where the runtime itself should own the live `Popen` handle

Cancellation behavior:

- `ToolRuntime` polls the child process
- `/stop` terminates the child process group
- timeouts can terminate the child process before it returns

This is narrower than `subprocess_json`, but it gives a reliable hard-stop boundary for command execution now.

## Why `subprocess_json` Instead Of Blanket Subprocess Execution

This matches the codebase better than a global switch:

- `ask_user_input` and `confirm_user_input` are inherently in-process and interactive
- some tools may eventually depend on namespace/runtime context
- many built-in file/search/system tools are already naturally serializable and are good candidates for isolation

This split gives hard-stop semantics where they are technically sound without lying about guarantees for tools that cannot support them.

## Proposed API Shape

Add optional execution metadata to `BaseTool` and callable tools.

### `BaseTool`

Add optional properties with safe defaults:

```python
class BaseTool(ABC):
    @property
    def execution_mode(self) -> str:
        return "inline"

    @property
    def timeout_seconds(self) -> float | None:
        return None
```

### Callable tools

Allow metadata via attributes:

```python
def search_code(pattern: str, path: str = ".") -> dict[str, object]:
    ...

search_code.execution_mode = "subprocess_json"
search_code.timeout_seconds = 30
```

## Tool Runtime Changes

### 1. Normalize execution metadata

Teach `ToolRuntime` to resolve a tool's execution metadata:

- `execution_mode`
- `timeout_seconds`
- whether the callable requests `shared_store`
- whether the tool is subprocess-eligible

### 2. Track active child process

Store cancellable execution state in `shared_store`, for example:

```python
shared_store["active_tool_execution"] = {
    "tool": tool_name,
    "mode": "subprocess_json",
    "pid": process.pid,
    "started_at": time.time(),
}
```

This lets the active `RunHandle` stop path reach a live tool process.

### 3. Add subprocess runner

Implement a private helper inside `ToolRuntime`:

```python
def _execute_tool_subprocess_json(...):
    ...
```

Responsibilities:

- serialize arguments to JSON
- launch a helper module with the tool import path and payload
- capture stdout/stderr
- parse JSON result
- enforce timeout
- terminate on cancellation request

### 4. Cancellation loop

While waiting on the child process:

- poll for process completion
- poll `run_cancel_requested`
- if cancellation is requested, terminate the child
- if termination does not complete quickly, kill the child

### 5. Event stream

Add runtime events for observability:

- `tool_subprocess_started`
- `tool_subprocess_terminated`
- `tool_subprocess_killed`
- `tool_timeout`

These should be additive; existing tool events remain intact.

## Helper Module

Add a small helper entrypoint, for example:

- `pocketcode/core/tool_subprocess_runner.py`

Inputs:

- tool import path
- JSON arguments

Outputs:

- a single JSON object to stdout

The helper should:

- import the tool object
- instantiate it if it is a `BaseTool` subclass
- reject tools that require `shared_store`
- execute the tool
- write a JSON result or structured error

## Initial Candidate Tools

These are good first candidates for `subprocess_json`:

- `core.read_file`
- `core.write_to_file`
- `core.list_files`
- `core.glob_files`
- `core.search_code`
- `core.execute_command`

These should remain `inline`:

- `core.ask_user_input`
- `core.confirm_user_input`
- any future tool that depends on live callbacks or mutable in-process state

## LLM Calls

Tool hard-stop and LLM hard-stop should be treated separately.

Recommended near-term position:

- keep LLM cancellation cooperative
- when the provider SDK supports request cancellation or client-side timeouts, expose those through `LlmRouter`
- do not block tool hard-stop work on provider cancellation support

## Failure Semantics

When a subprocess tool is terminated, the runtime should return a structured failure result such as:

```json
{
  "success": false,
  "error": "Tool 'core.execute_command' was terminated by cancellation.",
  "cancelled": true
}
```

When a timeout is hit:

```json
{
  "success": false,
  "error": "Tool 'core.execute_command' exceeded timeout (30s).",
  "timed_out": true
}
```

This keeps the runtime behavior deterministic and avoids pretending the tool completed normally.

## Rollout Plan

### Phase 1

- add execution metadata support to `BaseTool`
- add `ToolRuntime` support for `managed_subprocess`
- convert `core.execute_command` first
- add cancellation and timeout tests for that path

### Phase 2

- add subprocess helper runner
- add `ToolRuntime` support for broader `subprocess_json` tools
- convert file/search tools that do not depend on `shared_store`
- add runtime events for subprocess lifecycle
- surface tool timeout/cancel status in Textual run inspector

### Phase 3

- add optional config defaults in `pocketcode.yml`, for example per-tool timeout overrides
- document provider-specific LLM timeout knobs separately

## Testing Strategy

Add tests for:

- subprocess-eligible tool execution succeeds and returns JSON result
- `/stop` during subprocess tool execution terminates the child
- timeout kills a stuck subprocess tool
- tools requiring `shared_store` are rejected for subprocess mode
- inline tools continue to work exactly as they do now
- Textual/basic CLI surfaces display the right cancellation state

## Recommendation

Implement hard-stop support only for subprocess-eligible tools and keep everything else cooperative.

That gives Pocketcode a stop model with honest guarantees:

- runs always support cooperative cancellation
- eligible long-running tools support force-stop
- interactive and shared-state tools stay correct
