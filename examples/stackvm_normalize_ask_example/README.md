# StackVM Normalize Ask Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles plus selected fields into shared state, and then asks the user a follow-up question derived from that normalized view.

Layout:

- `flows/*.md`: registers the StackVM normalization flow
- `flows/normalize.md`: StackVM-backed normalization-and-question flow with `vm_module_prefixes` assigning the `common` helper prefix
- `vm/common.vm`: shared helper module for parsing and normalizing the tool-derived payload, loaded as `common.*`
- `vm/router.vm`: normalization script using `parallel-map`, `get-in?`, `bool>`, `shared!?`, `ask-user`, and qualified `common.*` helper calls

The example demonstrates:

- tool-first orchestration with `tool-request`
- normalization of tool-derived YAML into shared state
- fan-out normalization of all payload item titles with `parallel-map`
- question generation from normalized shared-state instead of the raw tool payload
- the `ask-user` transition as a first-class StackVM flow outcome
