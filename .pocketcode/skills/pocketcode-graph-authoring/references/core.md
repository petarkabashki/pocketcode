# PocketFlow Core

Primary sources:
- `pocketflow.py`
- `pocketflow.md`
- `docs/pocketflow_agents.md`

## Minimal execution model

`pocketflow.py` defines a graph plus shared-store runtime:
- a node reads from `shared` in `prep()`
- it computes in `exec()`
- it mutates shared state and returns an action in `post()`
- a `Flow` follows the returned action to the next successor

## Concrete semantics to preserve

- `Node(max_retries=..., wait=...)` retries only `exec()`
- `Flow._orch()` copies the current node before running it
- `curr >> next_node` creates a `default` edge
- `curr - "action" >> next_node` creates a labelled edge
- an unknown action ends the flow with a warning
- `Node.run()` does not traverse successors; `Flow.run()` does

## PocketCoder-specific usage

PocketCoder uses PocketFlow factories as namespace-backed flows:
- the factory must be zero-arg
- it should return `Flow(start=...)`
- a common single-node pattern is to return `llm_delegate` when `_llm_router` is present and `continue` otherwise

## Recommended design process

1. Design the shared-store keys first.
2. Choose whether you need plain, batch, async, or async-parallel behavior.
3. Keep `prep`, `exec`, and `post` narrowly scoped.
4. Wire the smallest graph that satisfies the task.
5. Verify the transitions actually match the strings returned by `post()`.
