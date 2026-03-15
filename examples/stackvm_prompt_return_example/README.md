# StackVM Prompt Return Example

This example shows a StackVM caller/delegate pair where the caller normalizes all payload item titles from tool-derived YAML, hands off with `return_to_caller`, the delegate prompts for a structured choice, and the caller finalizes from `last_delegated_result` after the delegate returns.

Layout:

- `flows` (*.md): registers the caller and delegate StackVM flows
- `normalize.md`: StackVM caller flow that loads the shared workspace stdlib io and normalization modules and hands off with a return policy
- `confirm_delegate.md`: StackVM delegate flow that prompts for a structured choice from one declarative decision table
- `vm/common.vm`: local helper facade that re-exports shared `stdlib.normalize` helpers under `common.*`
- `vm/router.vm`: caller script that binds a paired answer workflow declared in `vm/common.vm` through `define-choice-answer-family`, covering the full caller-side load, normalization, handoff, and finalization protocol, and calls qualified `common.*` helpers
- `vm/delegate.vm`: delegate script that binds the same `define-choice-answer-family` contract with `use-workflow-family` and returns a final answer to the caller

The example demonstrates:

- tool-first normalization of all payload item titles in a VM caller through `stdlib.io.read-yaml-file-once`
- shared file-read macros loaded from workspace-root `stdlib.io`
- shared normalization helpers loaded from workspace-root `stdlib.normalize`
- pure data fan-out with `parallel-map` before delegate handoff
- a paired answer workflow declared in `vm/common.vm` through `define-choice-answer-family` and bound with `use-workflow-family` for the full caller-side load, normalization, handoff, missing-answer handling, and finalization protocol
- structured delegate prompting through the same `define-choice-answer-family` contract
- caller-side finalization from `last_delegated_result` through a top-level return contract after a StackVM delegate returns
