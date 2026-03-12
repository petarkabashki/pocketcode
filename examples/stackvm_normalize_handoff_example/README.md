# StackVM Normalize Handoff Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles plus selected fields into shared state, and then hands off to different PocketFlow delegates based on the normalized result.

Layout:

- `flows/*.md`: registers the StackVM normalization router plus enabled and disabled delegates
- `flows/normalize.md`: StackVM-backed normalization-and-handoff flow
- `vm/common.vm`: shared word for parsing the tool result into payload data
- `vm/router.vm`: normalization script using `parallel-map`, `get-in?`, `bool>`, and `shared!?` before handoff
- `flows/enabled_delegate.py`: PocketFlow delegate for enabled normalized payloads
- `flows/disabled_delegate.py`: PocketFlow delegate for disabled normalized payloads

The example demonstrates:

- tool-first orchestration with `tool-request`
- normalization of tool-derived YAML into shared state
- fan-out normalization of all payload item titles with `parallel-map`
- handoff decisions based on normalized shared-store values rather than raw tool payload structure
- delegate flows that consume the normalized shared-state contract instead of re-parsing the payload