# StackVM Tool Normalize Example

This example shows a StackVM flow that reads a YAML payload through `core.read_file`, normalizes all payload item titles into shared state with `parallel-map`, and answers from the normalized view.

Layout:

- `plugin.yaml`: registers the VM normalization flow
- `flows/normalize.md`: StackVM-backed normalization flow
- `vm/common.vm`: shared word for parsing the tool result into payload data
- `vm/router.vm`: normalization script using `parallel-map`, `get-in?`, `bool>`, and `shared!?`

The example demonstrates:

- tool-first orchestration with `tool-request`
- YAML parsing from a tool result with `yaml>`
- safe extraction from nested tool-derived data with `get-in?`
- fan-out normalization of all payload item titles with `parallel-map`
- normalization into shared state with `shared!?`
- final answer generation from normalized shared-store values