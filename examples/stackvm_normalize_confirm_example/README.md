# StackVM Normalize Confirm Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles plus selected fields into shared state, prompts for a bridged user reply, and continues to a final answer in the same VM turn.

Layout:

- `flows/*.md`: registers the StackVM normalization flow
- `flows/normalize.md`: StackVM-backed normalization, prompt, and answer flow with `vm_module_prefixes` assigning the `common` helper prefix
- `vm/common.vm`: shared helper module for parsing and normalizing the tool-derived payload, loaded as `common.*`
- `vm/router.vm`: normalization script using `parallel-map`, `get-in?`, `shared!?`, `prompt-user`, `bool>`, and qualified `common.*` helper calls

The example demonstrates:

- tool-first orchestration with `tool-request`
- normalization of tool-derived YAML into shared state
- fan-out normalization of all payload item titles with `parallel-map`
- bridged text input with `prompt-user`
- continued VM execution after the user reply instead of terminating at a question surface
