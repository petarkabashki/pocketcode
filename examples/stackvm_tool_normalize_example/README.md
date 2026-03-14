# StackVM Tool Normalize Example

This example shows a StackVM flow that reads a YAML payload through `core.read_file`, normalizes all payload item titles into shared state with `parallel-map`, and answers from the normalized view.

Layout:

- `flows/*.md`: registers the VM normalization flow
- `flows/normalize.md`: StackVM-backed normalization flow with `vm_module_prefixes` assigning the `common` helper namespace
- `vm/common.vm`: shared helper module whose user-defined words are loaded under the `common.*` prefix
- `vm/router.vm`: normalization script using `tool-once`, `parallel-map`, `get-in?`, `bool>`, `shared!?`, and qualified `common.*` helper calls

The example demonstrates:

- tool-first orchestration with the built-in `tool-once` macro
- YAML parsing from a tool result with `yaml>`
- safe extraction from nested tool-derived data with `get-in?`
- fan-out normalization of all payload item titles with `parallel-map`
- normalization into shared state with `shared!?`
- final answer generation from normalized shared-store values
