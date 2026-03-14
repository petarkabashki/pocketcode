# StackVM Nested Structured Return Example

This example shows a StackVM caller/delegate pair where the caller normalizes all payload item titles, the delegate returns a nested YAML decision string, and the caller uses `get-in?` on the parsed return value before producing the final answer.

Layout:

- `flows/*.md`: registers the caller and VM delegate flows
- `flows/normalize.md`: caller flow that normalizes data, hands off, parses the returned nested YAML, and finalizes directly, with `vm_module_prefixes` assigning the `common` helper prefix
- `flows/confirm_delegate.md`: VM delegate flow that collects a structured choice and returns a nested YAML mapping string to the caller
- `vm/common.vm`: shared helper module for parsing and normalizing the tool-derived payload, loaded as `common.*`
- `vm/router.vm`: caller script that normalizes data with `parallel-map`, uses `tool-once` for the request loop, parses the returned YAML, reads nested fields with `get-in?`, uses `finalize-from` for the final answer, and calls qualified `common.*` helpers
- `vm/delegate.vm`: delegate script that collects a radio choice and returns a nested YAML mapping string

The example demonstrates:

- tool-first normalization of all payload item titles in a StackVM caller through `tool-once`
- pure data fan-out with `parallel-map` before delegate handoff
- `return_to_caller` handoff to a VM delegate
- nested YAML returned through `last_delegated_result.answer`
- caller-side parsing with `yaml>` plus nested reads with `get-in?`
- caller-side final answer construction through `finalize-from`
- default handling when an optional nested field is absent from the returned decision
