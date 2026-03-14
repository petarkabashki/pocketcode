# StackVM Normalize Ask Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles plus selected fields into shared state, and then asks the user a follow-up question derived from that normalized view.

Layout:

- `flows/*.md`: registers the StackVM normalization flow
- `flows/normalize.md`: StackVM-backed normalization-and-question flow loading the shared workspace stdlib io and normalization modules plus a local facade
- `vm/common.vm`: local helper facade that re-exports shared `stdlib.normalize` helpers under `common.*`
- `vm/router.vm`: normalization script using `stdlib.io.read-yaml-file-once`, `parallel-map`, `get-in?`, `bool>`, `shared!?`, `ask-from`, and qualified `common.*` helper calls

The example demonstrates:

- tool-first orchestration through the shared `stdlib.io.read-yaml-file-once` macro
- shared file-read macros loaded from workspace-root `stdlib.io`
- shared normalization helpers loaded from workspace-root `stdlib.normalize`
- normalization of tool-derived YAML into shared state
- fan-out normalization of all payload item titles with `parallel-map`
- question generation from normalized shared-state instead of the raw tool payload
- the built-in `ask-from` macro as the higher-level authoring form over `ask-user`
