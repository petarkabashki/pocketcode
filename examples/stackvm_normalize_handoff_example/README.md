# StackVM Normalize Handoff Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles plus selected fields into shared state, and then hands off to different PocketFlow delegates based on the normalized result.

Layout:

- `flows` (*.md): registers the StackVM normalization router plus enabled and disabled delegates
- `normalize.md`: StackVM-backed normalization-and-handoff flow loading the shared workspace stdlib io and normalization modules plus a local facade
- `vm/common.vm`: local helper facade that re-exports shared `stdlib.normalize` helpers under `common.*`
- `vm/router.vm`: normalization script using `stdlib.io.read-yaml-file-once`, `parallel-map`, `switch`, and qualified `common.*` helper calls before handoff
- `enabled_delegate.py`: PocketFlow delegate for enabled normalized payloads
- `disabled_delegate.py`: PocketFlow delegate for disabled normalized payloads

The example demonstrates:

- tool-first orchestration with the shared `stdlib.io.read-yaml-file-once` macro
- shared file-read macros loaded from workspace-root `stdlib.io`
- shared normalization helpers loaded from workspace-root `stdlib.normalize`
- normalization of tool-derived YAML into shared state
- fan-out normalization of all payload item titles with `parallel-map`
- exact-match enabled or disabled routing with `switch` after normalization
- handoff decisions based on normalized shared-store values rather than raw tool payload structure
- delegate flows that consume the normalized shared-state contract instead of re-parsing the payload
