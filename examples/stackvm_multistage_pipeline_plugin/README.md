# StackVM Multistage Pipeline Example

This example shows a two-stage StackVM pipeline where the caller normalizes all payload item titles from tool-derived YAML and collects checklist actions, then hands off to a VM delegate for a second structured decision, and finally resumes in the caller to produce the final answer.

If the first-stage checklist does not include `delegate`, the caller finalizes directly and skips the delegate stage.

Layout:

- `plugin.yaml`: registers the caller and delegate StackVM flows
- `flows/normalize.md`: caller flow that normalizes data, collects checklist actions, and finalizes after the delegate returns
- `flows/confirm_delegate.md`: delegate flow that collects a second structured decision
- `vm/common.vm`: shared word for parsing the tool result into payload data
- `vm/router.vm`: caller script that normalizes data with `parallel-map`, asks the first question, hands off, and finalizes on return
- `vm/delegate.vm`: delegate script that asks the second question and returns a final answer to the caller

The example demonstrates:

- tool-first normalization of all payload item titles in a StackVM caller
- pure data fan-out with `parallel-map` before the first structured interaction
- a first-stage checklist interaction in the caller
- a second-stage radio interaction in a VM delegate
- a direct caller-finalized branch when the first-stage selection does not require delegation
- `return_to_caller` handoff flow between VM stages
- finalization back in the caller from both the first-stage selection summary and `last_delegated_result`