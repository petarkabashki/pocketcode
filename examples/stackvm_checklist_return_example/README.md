# StackVM Checklist Return Example

This example shows a StackVM caller/delegate pair where the caller normalizes all tool-derived item titles, hands off with `return_to_caller`, the delegate collects multiple checklist selections, and the caller finalizes from `last_delegated_result` after the delegate returns.

Layout:

- `flows/*.md`: registers the caller and checklist delegate StackVM flows
- `flows/normalize.md`: StackVM caller flow that loads the shared workspace stdlib io and normalization modules and hands off with a return policy
- `flows/checklist_delegate.md`: StackVM delegate flow that collects multiple selections from one declarative decision table
- `vm/common.vm`: local helper facade that re-exports shared `stdlib.normalize` helpers under `common.*`
- `vm/router.vm`: caller script that binds a paired checklist answer workflow declared in `vm/common.vm` through `define-choice-answer-family`, covering the full caller-side load, normalization, handoff, and answer-composition protocol, and calls qualified `common.*` helpers
- `vm/delegate.vm`: delegate script that binds the same `define-choice-answer-family` contract with `contains` matching and `kind: checklist`

The example demonstrates:

- tool-first normalization of all payload item titles in a VM caller through `stdlib.io.read-yaml-file-once`
- shared file-read macros loaded from workspace-root `stdlib.io`
- shared normalization helpers loaded from workspace-root `stdlib.normalize`
- pure data fan-out with `parallel-map` before the delegate handoff
- a paired checklist answer workflow declared in `vm/common.vm` through `define-choice-answer-family` and bound with `use-workflow-family` for the full caller-side load, normalization, handoff, missing-answer handling, and answer-composition protocol
- checklist interaction through the same `define-choice-answer-family` contract with `contains` matching
- non-scalar `last_user_value` flowing through the handoff stack and `last_delegated_result`
- caller-side finalization from `last_delegated_result` through a top-level return contract
