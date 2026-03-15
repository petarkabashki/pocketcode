# StackVM Delegate Return Example

This example shows a StackVM caller/delegate pair where the caller normalizes tool-derived payload data, uses the built-in `return-delegate` macro for the standard return-to-caller handoff contract, and passes the delegate's final answer straight back through the caller.

Layout:

- `flows` (*.md): registers the caller and delegate StackVM flows
- `normalize.md`: StackVM caller flow that loads the shared workspace stdlib io and normalization modules, sets a return policy, and passes the delegate answer through
- `confirm_delegate.md`: StackVM delegate flow that collects a structured choice from one declarative decision table and answers directly
- `vm/common.vm`: local helper facade that re-exports shared `stdlib.normalize` helpers under `common.*`
- `vm/router.vm`: caller script that uses `stdlib.io.read-yaml-file-once` for the file-loading turn, `return-delegate` for the pass-through return branch, and qualified `common.*` helper calls
- `vm/delegate.vm`: delegate script that uses `workflow-spec` and returns a final answer string to the caller

The example demonstrates:

- tool-first normalization of all payload item titles in a VM caller through `stdlib.io.read-yaml-file-once`
- shared file-read macros loaded from workspace-root `stdlib.io`
- shared normalization helpers loaded from workspace-root `stdlib.normalize`
- pure data fan-out with `parallel-map` before delegate handoff
- the built-in `return-delegate` macro for the standard `return_to_caller` setup plus pass-through return behavior
- direct pass-through of `last_delegated_result.answer` through `return-delegate`
- a checked-in reference for the current `return-delegate` macro contract

Conceptually, `return-delegate` expands to the same explicit “handoff when the delegated result is missing, otherwise answer from the returned path” branch that a handwritten router would use, but with the checked-in return policy generated for you.
