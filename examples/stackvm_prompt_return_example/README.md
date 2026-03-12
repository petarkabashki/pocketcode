# StackVM Prompt Return Example

This example shows a StackVM caller/delegate pair where the caller normalizes all payload item titles from tool-derived YAML, hands off with `return_to_caller`, the delegate prompts for a structured choice, and the caller finalizes from `last_delegated_result` after the delegate returns.

Layout:

- `flows/*.md`: registers the caller and delegate StackVM flows
- `flows/normalize.md`: StackVM caller flow that normalizes data and hands off with a return policy
- `flows/confirm_delegate.md`: StackVM delegate flow that prompts for a structured choice
- `vm/common.vm`: shared word for parsing the tool result into payload data
- `vm/router.vm`: caller script that normalizes data with `parallel-map`, uses `tool-once` for the request loop, and uses `finalize-from` for caller-side answer composition
- `vm/delegate.vm`: delegate script that uses `prompt-interaction` and returns a final answer to the caller

The example demonstrates:

- tool-first normalization of all payload item titles in a VM caller through `tool-once`
- pure data fan-out with `parallel-map` before delegate handoff
- `pending_handoff_policy` with `return_to_caller: true`
- structured delegate prompting with `prompt-interaction`
- caller-side finalization from `last_delegated_result` through `finalize-from` after a StackVM delegate returns
