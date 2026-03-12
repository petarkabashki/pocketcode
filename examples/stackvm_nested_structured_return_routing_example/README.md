# StackVM Nested Structured Return Routing Example

This example shows a StackVM caller/delegate pair where the caller normalizes all payload item titles, the delegate returns a nested YAML decision string, and the caller uses `get-in?` on the parsed return value to choose the final downstream route.

Layout:

- `flows/*.md`: registers the caller flow, VM delegate, and final route delegates
- `flows/normalize.md`: caller flow that normalizes data, hands off, parses the returned nested YAML, and routes to the final delegate
- `flows/confirm_delegate.md`: VM delegate flow that collects a structured choice and returns a nested YAML mapping string to the caller
- `flows/approve_route.py`: PocketFlow delegate for approve decisions
- `flows/escalate_route.py`: PocketFlow delegate for escalate decisions
- `flows/review_route.py`: PocketFlow delegate for review decisions
- `vm/common.vm`: shared word for parsing the tool result into payload data
- `vm/router.vm`: caller script that normalizes data with `parallel-map`, uses `tool-once` for the request loop, parses the returned YAML, reads nested fields with `get-in?`, and routes to the final delegate
- `vm/delegate.vm`: delegate script that collects a radio choice and returns a nested YAML mapping string to the caller

The example demonstrates:

- tool-first normalization of all payload item titles in a StackVM caller through `tool-once`
- pure data fan-out with `parallel-map` before the delegate handoff
- `return_to_caller` handoff to a VM delegate
- nested YAML returned through `last_delegated_result.answer`
- caller-side parsing with `yaml>` plus nested reads with `get-in?`
- caller-side routing to different downstream delegates from nested returned fields
- default handling when an optional nested field is absent from the returned decision
