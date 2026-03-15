# StackVM Buttons Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles into shared state, presents structured button choices, and continues to a final answer from the selected option.

Layout:

- `flows` (*.md): registers the StackVM normalization flow
- `normalize.md`: StackVM-backed normalization, interaction, and answer flow loading the shared workspace stdlib io and normalization modules plus a local helper facade
- `vm/common.vm`: local helper module re-exporting the shared `stdlib.normalize` helpers under `common.*`
- `vm/router.vm`: normalization script using a direct continuation contract declared in `vm/common.vm` with `define-choice-continue-spec` and bound with `use-workflow-spec` plus qualified `common.*` helper calls

The example demonstrates:

- loading shared file-read macros from workspace-root `stdlib.io`
- loading shared normalization helpers from workspace-root `stdlib.normalize`
- tool-first orchestration with the shared `stdlib.io.read-yaml-file-once` macro
- normalization of all tool-derived item titles into shared state
- pure data fan-out with `parallel-map` before the interaction step
- structured `buttons` interaction through `define-choice-continue-spec` in `vm/common.vm` and `use-workflow-spec` in the router, which packages file load, normalization, normalized-summary prompt construction, and direct `continue` plus `exact` choice routing
- continued VM execution from the selected option value

Conceptually, the named workflow-spec layer moves the example up another level: `vm/common.vm` declares the payload source, normalization contract, normalized-summary prompt prefix, option table, and continuation behavior once, and `vm/router.vm` just binds that contract by role and policy.
