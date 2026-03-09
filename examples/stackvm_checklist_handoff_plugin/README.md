# StackVM Checklist Handoff Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles into shared state, collects checklist actions, formats them with `join`, and then hands off to different delegates based on the selected list.

Layout:

- `plugin.yaml`: registers the StackVM caller flow and the downstream delegates
- `flows/normalize.md`: StackVM-backed normalization, checklist interaction, and routing flow
- `flows/delegate_route.py`: PocketFlow delegate for selections containing `delegate`
- `flows/approve_route.py`: PocketFlow delegate for selections containing `approve` when `delegate` is absent
- `flows/review_route.py`: PocketFlow delegate for remaining selections
- `vm/common.vm`: shared word for parsing the tool result into payload data
- `vm/router.vm`: normalization and checklist-driven handoff routing script using `parallel-map`

The example demonstrates:

- tool-first normalization of all payload item titles in a StackVM flow
- pure data fan-out with `parallel-map` before the interaction step
- checklist interaction through `prompt-interaction`
- readable selection formatting with `join`
- routing to different delegates based on membership in the selected action list