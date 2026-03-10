# StackVM Checklist Return Example

This example shows a StackVM caller/delegate pair where the caller normalizes all tool-derived item titles, hands off with `return_to_caller`, the delegate collects multiple checklist selections, and the caller finalizes from `last_delegated_result` after the delegate returns.

Layout:

- `plugin.yaml`: registers the caller and checklist delegate StackVM flows
- `flows/normalize.md`: StackVM caller flow that normalizes data and hands off with a return policy
- `flows/checklist_delegate.md`: StackVM delegate flow that collects multiple selections
- `vm/common.vm`: shared word for parsing the tool result into payload data
- `vm/router.vm`: caller script that normalizes data with `parallel-map`, uses `tool-once` for the request loop, and uses `finalize-from` for caller-side answer composition
- `vm/delegate.vm`: delegate script that uses `prompt-interaction` with `kind: checklist`

The example demonstrates:

- tool-first normalization of all payload item titles in a VM caller through `tool-once`
- pure data fan-out with `parallel-map` before the delegate handoff
- `pending_handoff_policy` with `return_to_caller: true`
- checklist interaction through `prompt-interaction`
- non-scalar `last_user_value` flowing through the handoff stack and `last_delegated_result`
- caller-side finalization from `last_delegated_result` through `finalize-from`
