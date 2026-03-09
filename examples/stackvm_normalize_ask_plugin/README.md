# StackVM Normalize Ask Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles plus selected fields into shared state, and then asks the user a follow-up question derived from that normalized view.

Layout:

- `plugin.yaml`: registers the StackVM normalization flow
- `flows/normalize.md`: StackVM-backed normalization-and-question flow
- `vm/common.vm`: shared word for parsing the tool result into payload data
- `vm/router.vm`: normalization script using `parallel-map`, `get-in?`, `bool>`, `shared!?`, and `ask-user`

The example demonstrates:

- tool-first orchestration with `tool-request`
- normalization of tool-derived YAML into shared state
- fan-out normalization of all payload item titles with `parallel-map`
- question generation from normalized shared-state instead of the raw tool payload
- the `ask-user` transition as a first-class StackVM flow outcome