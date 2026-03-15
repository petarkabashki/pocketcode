# StackVM Radio Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles into shared state, presents a radio-style structured choice, and continues to a final answer from the selected mode.

Layout:

- `flows` (*.md): registers the StackVM normalization flow
- `normalize.md`: StackVM-backed normalization, radio interaction, and answer flow loading the shared workspace stdlib io and normalization modules plus a local facade
- `vm/common.vm`: local helper facade that re-exports shared `stdlib.normalize` helpers under `common.*`
- `vm/router.vm`: normalization script using a direct continuation contract declared in `vm/common.vm` with `define-choice-continue-spec` and bound with `use-workflow-spec` plus qualified `common.*` helper calls

The example demonstrates:

- tool-first orchestration with the shared `stdlib.io.read-yaml-file-once` macro
- shared file-read macros loaded from workspace-root `stdlib.io`
- shared normalization helpers loaded from workspace-root `stdlib.normalize`
- normalization of all tool-derived item titles into shared state
- pure data fan-out with `parallel-map` before the interaction step
- structured `radio` interaction through `define-choice-continue-spec` in `vm/common.vm` and `use-workflow-spec` in `continue` plus `exact` mode
- continued VM execution from the selected mode value

This example now uses `define-choice-continue-spec` rather than separate file-load, normalization, prompt-building, and routing macros, so the router binds one declared radio option table and exact-match answer policy from `vm/common.vm`.
