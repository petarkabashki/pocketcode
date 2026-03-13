# PocketFlow Sources

Primary sources:
- `pocketflow.py`
- `pocketflow.md`
- `docs/pocketflow_agents.md`

## What the runtime actually does

`pocketflow.py` defines the execution model:
- `BaseNode` stores `params` and `successors`.
- `Node` adds retry behavior via `max_retries` and `wait`.
- `Flow` copies the current node before each step and repeatedly follows the action returned by `post()`.
- `BatchNode` and `BatchFlow` loop over items or parameter batches.
- `AsyncNode`, `AsyncFlow`, and parallel async variants define the async behavior.

Key implications from `pocketflow.py`:
- `prep(shared)` reads from the shared store.
- `exec(prep_res)` should be the main computation step.
- `post(shared, prep_res, exec_res)` mutates shared state and returns the next action.
- Missing or unmatched actions end the flow.
- Running a bare `Node` with successors only warns; `Flow` is what traverses successors.

## How PocketCoder uses PocketFlow

`docs/pocketflow_agents.md` and the runtime show the practical pattern:
- PocketCoder agents are PocketFlow `Flow` factories registered through resource-root and namespace asset loading.
- A standard PocketCoder flow often uses one node whose `post()` returns `llm_delegate` when `_llm_router` is available.
- Shared store keys commonly used by PocketCoder:
  - `initial_request`
  - `task`
  - `results`
  - `_llm_router`
  - `_tool_runtime`
  - `_registry`

## Authoring checklist

When editing a PocketFlow-based agent:
1. Choose the smallest node/flow type that fits.
2. Keep `prep/exec/post` responsibilities separate.
3. Return explicit transition strings from `post()`.
4. Register the zero-arg factory from the owning Markdown or Python-backed namespace asset.
5. Verify the flow is compatible with PocketCoder shared-store conventions.

## Patterns to preserve

Prefer these patterns in PocketCoder flows:
- `prep()` uses `shared.get("initial_request", shared.get("task", ""))`
- `post()` records a fallback result when `_llm_router` is absent
- `create_flow()` returns `Flow(start=...)`

Avoid:
- hiding critical shared-store mutations in `exec()`
- relying on repo-specific global state instead of `shared`
- adding complex graph branching when a single-node flow is sufficient
