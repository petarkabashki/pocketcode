# StackVM Structured Return Finalize Example

This example shows a StackVM caller/delegate pair where the caller normalizes all payload item titles, the delegate returns a structured YAML decision string, and the caller parses that value to produce the final answer directly.

Layout:

- `flows/*.md`: registers the caller and VM delegate flows
- `flows/normalize.md`: caller flow that normalizes data, hands off, parses the returned YAML decision, and finalizes directly
- `flows/confirm_delegate.md`: VM delegate flow that collects a structured choice and returns a YAML decision string to the caller
- `vm/common.vm`: shared word for parsing the tool result into payload data
- `vm/router.vm`: caller script that normalizes data with `parallel-map`, uses `tool-once` for the request loop, parses the returned YAML, and uses `finalize-from` for the final answer
- `vm/delegate.vm`: delegate script that collects a radio choice and returns a YAML mapping string to the caller

The example demonstrates:

- tool-first normalization of all payload item titles in a StackVM caller through `tool-once`
- pure data fan-out with `parallel-map` before delegate handoff
- `return_to_caller` handoff to a VM delegate
- delegate answers encoded as stable YAML strings instead of free-form text
- caller-side parsing of `last_delegated_result.answer` with `yaml>`
- final answer construction in the caller from returned structured fields through `finalize-from` rather than a downstream route
