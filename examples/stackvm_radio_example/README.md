# StackVM Radio Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles into shared state, presents a radio-style structured choice, and continues to a final answer from the selected mode.

Layout:

- `flows/*.md`: registers the StackVM normalization flow
- `flows/normalize.md`: StackVM-backed normalization, radio interaction, and answer flow with `vm_module_prefixes` assigning the `common` helper prefix
- `vm/common.vm`: shared helper module for parsing and normalizing the tool-derived payload, loaded as `common.*`
- `vm/router.vm`: normalization script using `tool-once`, `dict-get?`, `parallel-map`, `shared!?`, `dict-set`, `prompt-interaction`, and qualified `common.*` helper calls

The example demonstrates:

- tool-first orchestration with the built-in `tool-once` macro
- normalization of all tool-derived item titles into shared state
- pure data fan-out with `parallel-map` before the interaction step
- structured `radio` interaction through direct `prompt-interaction`
- continued VM execution from the selected mode value

This example intentionally keeps `prompt-interaction` instead of `prompt-route` because it formats the selected value directly after the interaction rather than immediately routing through exact-match cases.
