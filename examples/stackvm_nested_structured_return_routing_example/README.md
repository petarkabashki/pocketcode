# StackVM Nested Structured Return Routing Example

This example shows a StackVM caller/delegate pair where the caller normalizes all payload item titles, the delegate returns a nested YAML decision string, and the caller routes from declarative nested field specs instead of embedding `get-in?` logic inline.

Layout:

- `flows/*.md`: registers the caller flow, VM delegate, and final route delegates
- `flows/normalize.md`: caller flow that loads the shared workspace stdlib io and normalization modules, hands off, then resumes through the paired nested structured route workflow
- `flows/confirm_delegate.md`: VM delegate flow that collects a structured choice from one declarative decision table and returns a nested YAML mapping string to the caller
- `flows/approve_route.py`: PocketFlow delegate for approve decisions
- `flows/escalate_route.py`: PocketFlow delegate for escalate decisions
- `flows/review_route.py`: PocketFlow delegate for review decisions
- `vm/common.vm`: local helper facade that re-exports shared `stdlib.normalize` helpers under `common.*`
- `vm/router.vm`: caller script that binds the caller half of `define-choice-route-family` for the full caller-side load, normalization, handoff, YAML resume protocol, nested field projection with defaults, and final routing policy, and calls qualified `common.*` helpers
- `vm/delegate.vm`: delegate script that binds the delegate half of `define-choice-route-family`, collects a radio choice, declares nested returned fields as path/value specs, layers them onto a shared base mapping, and emits YAML at the answer boundary

The example demonstrates:

- tool-first normalization of all payload item titles in a StackVM caller through `stdlib.io.read-yaml-file-once`
- shared file-read macros loaded from workspace-root `stdlib.io`
- shared normalization helpers loaded from workspace-root `stdlib.normalize`
- pure data fan-out with `parallel-map` before the delegate handoff
- a paired nested structured route workflow declared in `vm/common.vm` through `define-choice-route-family` and bound with `use-workflow-family` for the full caller-side load, normalization, handoff, returned-decision parsing, nested field projection, and routing protocol
- nested YAML returned through `last_delegated_result.answer`
- caller-side routing from declarative nested field-spec triples with explicit defaults
- caller-side routing to different downstream delegates from nested returned fields
- default handling when an optional nested field is absent from the returned decision
