# StackVM Normalize Confirm Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles plus selected fields into shared state, prompts for a bridged user reply, and continues to a final answer in the same VM turn.

Layout:

- `flows/*.md`: registers the StackVM normalization flow
- `flows/normalize.md`: StackVM-backed normalization, prompt, and answer flow loading the shared workspace stdlib io and normalization modules plus a local facade
- `vm/common.vm`: local helper facade that re-exports shared `stdlib.normalize` helpers under `common.*`
- `vm/router.vm`: normalization script using `stdlib.io.read-yaml-file-once`, `parallel-map`, `get-in?`, `shared!?`, `prompt-store-text`, `bool>`, and qualified `common.*` helper calls

The example demonstrates:

- tool-first orchestration through the shared `stdlib.io.read-yaml-file-once` macro
- shared file-read macros loaded from workspace-root `stdlib.io`
- shared normalization helpers loaded from workspace-root `stdlib.normalize`
- normalization of tool-derived YAML into shared state
- fan-out normalization of all payload item titles with `parallel-map`
- bridged text input with the built-in `prompt-store-text` macro
- continued VM execution after the user reply instead of terminating at a question surface
