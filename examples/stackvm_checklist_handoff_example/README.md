# StackVM Checklist Handoff Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles into shared state, collects checklist actions, formats them with `join`, and then hands off to different delegates based on the selected list.

Layout:

- `flows/*.md`: registers the StackVM caller flow and the downstream delegates
- `flows/normalize.md`: StackVM-backed normalization, checklist interaction, and routing flow loading the shared workspace stdlib io and normalization modules plus a local helper facade
- `flows/delegate_route.py`: PocketFlow delegate for selections containing `delegate`
- `flows/approve_route.py`: PocketFlow delegate for selections containing `approve` when `delegate` is absent
- `flows/review_route.py`: PocketFlow delegate for remaining selections
- `vm/common.vm`: local helper module re-exporting the shared `stdlib.normalize` helpers under `common.*`
- `vm/router.vm`: normalization and checklist-driven handoff routing script using a continuation contract declared in `vm/common.vm` with `define-choice-continue-spec` and bound with `use-workflow-spec` plus qualified `common.*` helper calls

The example demonstrates:

- loading shared file-read macros from workspace-root `stdlib.io`
- loading shared normalization and selection-formatting helpers from workspace-root `stdlib.normalize`
- tool-first normalization of all payload item titles through `stdlib.io.read-yaml-file-once`
- pure data fan-out with `parallel-map` before the interaction step
- checklist interaction through `define-choice-continue-spec` in `vm/common.vm` and `use-workflow-spec` in `continue` plus `contains` mode
- readable selection formatting with `join`
- routing to different delegates based on membership in the selected action list
