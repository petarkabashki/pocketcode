# StackVM Normalize Confirm Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles plus selected fields into shared state, prompts for a bridged user reply, and continues to a final answer in the same VM turn.

Layout:

- `flows/*.md`: registers the StackVM normalization flow
- `flows/normalize.md`: StackVM-backed normalization, prompt, and answer flow
- `vm/common.vm`: shared word for parsing the tool result into payload data
- `vm/router.vm`: normalization script using `parallel-map`, `get-in?`, `shared!?`, `prompt-user`, and `bool>`

The example demonstrates:

- tool-first orchestration with `tool-request`
- normalization of tool-derived YAML into shared state
- fan-out normalization of all payload item titles with `parallel-map`
- bridged text input with `prompt-user`
- continued VM execution after the user reply instead of terminating at a question surface