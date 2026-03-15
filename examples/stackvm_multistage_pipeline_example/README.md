# StackVM Multistage Pipeline Example

This example shows a two-stage StackVM pipeline where the caller normalizes all payload item titles from tool-derived YAML and collects checklist actions through `define-choice-continue-answer-family`, then hands off to a VM delegate for a second structured decision, and finally resumes in the caller to produce the final answer.

If the first-stage checklist does not include `delegate`, the caller finalizes directly and skips the delegate stage.

Layout:

- `flows` (*.md): registers the caller and delegate StackVM flows
- `normalize.md`: caller flow that loads the shared workspace stdlib io and normalization modules, collects checklist actions, and finalizes after the delegate returns
- `confirm_delegate.md`: delegate flow that collects a second structured decision from one declarative decision table
- `vm/common.vm`: local helper facade that re-exports shared `stdlib.normalize` helpers under `common.*`
- `vm/router.vm`: caller script that binds the router half of `define-choice-continue-answer-family` for the file-loading, normalization, normalized-summary prompt, and first-stage checklist policy, then hands off or finalizes directly through qualified `common.*` helpers
- `vm/delegate.vm`: delegate script that binds the delegate half of `define-choice-continue-answer-family`, asks the second question, and returns a final answer to the caller

The example demonstrates:

- tool-first normalization of all payload item titles in a StackVM caller through `stdlib.io.read-yaml-file-once`
- shared file-read macros loaded from workspace-root `stdlib.io`
- shared normalization helpers loaded from workspace-root `stdlib.normalize`
- pure data fan-out with `parallel-map` before the first structured interaction
- a first-stage checklist interaction in the caller
- a second-stage radio interaction in a VM delegate
- a direct caller-finalized branch when the first-stage selection does not require delegation
- the built-in `return-handoff` macro for the standard `return_to_caller` handoff flow between VM stages
- finalization back in the caller from both the first-stage selection summary and `last_delegated_result` through `finalize-from`
