# StackVM Parallel Map Example

This example shows a StackVM flow that fans out over a fixed list with `parallel-map`, reuses a user-defined helper word inside each child VM, and answers from the collected result list.

Layout:

- `plugin.yaml`: registers the StackVM flow
- `flows/map.md`: StackVM-backed pure data transform flow
- `vm/router.vm`: helper-word and `parallel-map` script

The example demonstrates:

- pure data fan-out with `parallel-map`
- replay of user-defined words inside child VMs spawned by `parallel-map`
- joining the mapped result list into a user-facing answer

This example intentionally avoids `tool-request`, `handoff`, and interaction words so the focus stays on the `parallel-map` contract.