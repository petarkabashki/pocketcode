---
name: pocketflow-graph-authoring
description: Use when creating or editing PocketFlow nodes and flows for PocketCoder. Covers Node, Flow, Batch, Async, retries, shared-store patterns, and how PocketFlow factories are used by PocketCoder plugin flows.
tools:
  - core.read_file
  - core.search_code
---
Use this skill for pure PocketFlow graph authoring.

Read first:
- `references/core.md`

Then:
- inspect the target flow implementation
- keep the graph as small as possible
- follow the actual semantics from `pocketflow.py`, not generic workflow assumptions

When editing a PocketCoder flow:
- use PocketFlow for control flow
- use the shared store for state exchange
- keep the runtime handoff pattern compatible with PocketCoder, especially `_llm_router`, `_tool_runtime`, and `_registry`

