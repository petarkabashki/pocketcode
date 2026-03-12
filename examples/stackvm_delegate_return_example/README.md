# StackVM Delegate Return Example

This example shows a StackVM caller/delegate pair where the caller normalizes tool-derived payload data, hands off with `return_to_caller`, and passes the delegate's final answer straight back through the built-in `delegate-return` macro.

Layout:

- `flows/*.md`: registers the caller and delegate StackVM flows
- `flows/normalize.md`: StackVM caller flow that normalizes data, sets a return policy, and passes the delegate answer through
- `flows/confirm_delegate.md`: StackVM delegate flow that collects a structured choice and answers directly
- `vm/common.vm`: shared word set for parsing and normalizing the tool-derived payload
- `vm/router.vm`: caller script that uses `tool-once` for the tool loop and `delegate-return` for the pass-through return branch
- `vm/delegate.vm`: delegate script that uses `prompt-interaction` and returns a final answer string to the caller

The example demonstrates:

- tool-first normalization of all payload item titles in a VM caller through `tool-once`
- pure data fan-out with `parallel-map` before delegate handoff
- explicit `pending_handoff_policy` setup with `return_to_caller: true`
- direct pass-through of `last_delegated_result.answer` through `delegate-return`
- a checked-in reference for the current `delegate-return` macro contract

Conceptually, `delegate-return` expands to the same explicit “handoff when the delegated result is missing, otherwise answer from the returned path” branch that a handwritten router would use. The return policy still stays explicit in the caller.
