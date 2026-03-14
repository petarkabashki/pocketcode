# StackVM Structured Return Routing Example

This example shows a StackVM caller/delegate pair where the caller normalizes all payload item titles, the delegate returns a structured YAML decision string, and the caller parses that returned value to choose the final downstream route.

Layout:

- `flows/*.md`: registers the caller flow, VM delegate, and final route delegates
- `flows/normalize.md`: caller flow that normalizes data, hands off, parses the returned YAML decision, and routes to the final delegate, with `vm_module_prefixes` assigning the `common` helper prefix
- `flows/confirm_delegate.md`: VM delegate flow that collects a structured choice and returns a YAML decision string to the caller
- `flows/approve_route.py`: PocketFlow delegate for approve decisions
- `flows/escalate_route.py`: PocketFlow delegate for escalate decisions
- `flows/review_route.py`: PocketFlow delegate for review decisions
- `vm/common.vm`: shared helper module for parsing and normalizing the tool-derived payload, loaded as `common.*`
- `vm/router.vm`: caller script that normalizes data with `parallel-map`, uses `tool-once` for the request loop, parses the returned YAML, routes to the final delegate, and calls qualified `common.*` helpers
- `vm/delegate.vm`: delegate script that collects a radio choice and returns a YAML mapping string to the caller

The example demonstrates:

- tool-first normalization of all payload item titles in a StackVM caller through `tool-once`
- pure data fan-out with `parallel-map` before the delegate handoff
- `return_to_caller` handoff to a VM delegate
- delegate answers encoded as stable YAML strings instead of free-form text
- caller-side parsing of `last_delegated_result.answer` with `yaml>`
- final routing to different downstream delegates from the parsed delegate decision
