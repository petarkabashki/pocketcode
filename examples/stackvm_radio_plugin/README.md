# StackVM Radio Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles into shared state, presents a radio-style structured choice, and continues to a final answer from the selected mode.

Layout:

- `plugin.yaml`: registers the StackVM normalization flow
- `flows/normalize.md`: StackVM-backed normalization, radio interaction, and answer flow
- `vm/common.vm`: shared word for parsing the tool result into payload data
- `vm/router.vm`: normalization script using `tool-once`, `dict-get?`, `parallel-map`, `shared!?`, `dict-set`, and `prompt-interaction`

The example demonstrates:

- tool-first orchestration with the built-in `tool-once` macro
- normalization of all tool-derived item titles into shared state
- pure data fan-out with `parallel-map` before the interaction step
- structured `radio` interaction through direct `prompt-interaction`
- continued VM execution from the selected mode value

This example intentionally keeps `prompt-interaction` instead of `prompt-route` because it formats the selected value directly after the interaction rather than immediately routing through exact-match cases.
