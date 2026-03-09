# StackVM Nested Structured Return Example

This example shows a StackVM caller/delegate pair where the caller normalizes all payload item titles, the delegate returns a nested YAML decision string, and the caller uses `get-in?` on the parsed return value before producing the final answer.

Layout:

- `plugin.yaml`: registers the caller and VM delegate flows
- `flows/normalize.md`: caller flow that normalizes data, hands off, parses the returned nested YAML, and finalizes directly
- `flows/confirm_delegate.md`: VM delegate flow that collects a structured choice and returns a nested YAML mapping string to the caller
- `vm/common.vm`: shared word for parsing the tool result into payload data
- `vm/router.vm`: caller script that normalizes data with `parallel-map`, hands off, parses the returned YAML, reads nested fields with `get-in?`, and constructs the final answer
- `vm/delegate.vm`: delegate script that collects a radio choice and returns a nested YAML mapping string

The example demonstrates:

- tool-first normalization of all payload item titles in a StackVM caller
- pure data fan-out with `parallel-map` before delegate handoff
- `return_to_caller` handoff to a VM delegate
- nested YAML returned through `last_delegated_result.answer`
- caller-side parsing with `yaml>` plus nested reads with `get-in?`
- default handling when an optional nested field is absent from the returned decision
