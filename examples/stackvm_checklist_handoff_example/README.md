# StackVM Checklist Handoff Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles into shared state, collects checklist actions, formats them with `join`, and then hands off to different delegates based on the selected list.

Layout:

- `flows/*.md`: registers the StackVM caller flow and the downstream delegates
- `flows/normalize.md`: StackVM-backed normalization, checklist interaction, and routing flow with `vm_module_prefixes` assigning the `common` helper prefix
- `flows/delegate_route.py`: PocketFlow delegate for selections containing `delegate`
- `flows/approve_route.py`: PocketFlow delegate for selections containing `approve` when `delegate` is absent
- `flows/review_route.py`: PocketFlow delegate for remaining selections
- `vm/common.vm`: shared helper module for parsing and normalizing the tool-derived payload, loaded as `common.*`
- `vm/router.vm`: normalization and checklist-driven handoff routing script using `parallel-map` and qualified `common.*` helper calls

The example demonstrates:

- tool-first normalization of all payload item titles in a StackVM flow
- pure data fan-out with `parallel-map` before the interaction step
- checklist interaction through `prompt-interaction`
- readable selection formatting with `join`
- routing to different delegates based on membership in the selected action list
