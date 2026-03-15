# StackVM Tool Normalize Example

This example shows a StackVM flow that reads a YAML payload through the shared `stdlib.io.read-yaml-file-once` macro, normalizes all payload item titles into shared state with `parallel-map`, and answers from the normalized view.

Layout:

- `flows` (*.md): registers the VM normalization flow
- `normalize.md`: StackVM-backed normalization flow loading the shared workspace stdlib io and normalization modules plus a local facade
- `vm/common.vm`: local helper facade that re-exports shared `stdlib.normalize` helpers under `common.*`
- `vm/router.vm`: normalization script using `stdlib.io.read-yaml-file-once`, `parallel-map`, `get-in?`, `bool>`, `shared!?`, and qualified `common.*` helper calls

The example demonstrates:

- tool-first orchestration with the shared `stdlib.io.read-yaml-file-once` macro
- shared file-read macros loaded from workspace-root `stdlib.io`
- shared normalization helpers loaded from workspace-root `stdlib.normalize`
- YAML parsing from a tool result with `yaml>`
- safe extraction from nested tool-derived data with `get-in?`
- fan-out normalization of all payload item titles with `parallel-map`
- normalization into shared state with `shared!?`
- final answer generation from normalized shared-store values
