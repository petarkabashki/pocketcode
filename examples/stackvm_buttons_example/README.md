# StackVM Buttons Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles into shared state, presents structured button choices, and continues to a final answer from the selected option.

Layout:

- `flows/*.md`: registers the StackVM normalization flow
- `flows/normalize.md`: StackVM-backed normalization, interaction, and answer flow with `vm_module_prefixes` assigning the `common` helper prefix
- `vm/common.vm`: shared helper module for parsing the tool result into payload data, loaded as `common.*`
- `vm/router.vm`: normalization script using `tool-once`, `prompt-route`, `dict-get?`, `parallel-map`, `shared!?`, `dict-set`, and qualified `common.*` helper calls

The example demonstrates:

- tool-first orchestration with the built-in `tool-once` macro
- normalization of all tool-derived item titles into shared state
- pure data fan-out with `parallel-map` before the interaction step
- structured `buttons` interaction through the built-in `prompt-route` macro
- continued VM execution from the selected option value

Conceptually, `prompt-route` expands to the same `prompt-interaction` plus `switch` pattern the runtime already supports, but it keeps the router focused on the case table instead of the plumbing.
