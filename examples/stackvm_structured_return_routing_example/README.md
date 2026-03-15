# StackVM Structured Return Routing Example

This example shows a StackVM caller/delegate pair where the caller normalizes all payload item titles, the delegate returns a structured YAML decision string, and the caller routes from declarative returned-field specs instead of hand-written projection code.

Layout:

- `flows` (*.md): registers the caller flow, VM delegate, and final route delegates
- `normalize.md`: caller flow that loads the shared workspace stdlib io and normalization modules, hands off, then resumes through the paired structured route workflow
- `confirm_delegate.md`: VM delegate flow that collects a structured choice from one declarative decision table and returns a YAML decision string to the caller
- `approve_route.py`: PocketFlow delegate for approve decisions
- `escalate_route.py`: PocketFlow delegate for escalate decisions
- `review_route.py`: PocketFlow delegate for review decisions
- `vm/common.vm`: local helper facade that re-exports shared `stdlib.normalize` helpers under `common.*`
- `vm/router.vm`: caller script that binds the caller half of `define-choice-route-family` for the full caller-side load, normalization, handoff, YAML resume protocol, declarative returned-field projection, and final routing policy, and calls qualified `common.*` helpers
- `vm/delegate.vm`: delegate script that binds the delegate half of `define-choice-route-family`, collects a radio choice, declares returned fields as path/value specs, and emits YAML only at the answer boundary

The example demonstrates:

- tool-first normalization of all payload item titles in a StackVM caller through `stdlib.io.read-yaml-file-once`
- shared file-read macros loaded from workspace-root `stdlib.io`
- shared normalization helpers loaded from workspace-root `stdlib.normalize`
- pure data fan-out with `parallel-map` before the delegate handoff
- a paired structured route workflow declared in `vm/common.vm` through `define-choice-route-family` and bound with `use-workflow-family` for the full caller-side load, normalization, handoff, returned-decision parsing, field projection, and resumed routing protocol
- delegate answers encoded as stable YAML strings instead of free-form text
- caller-side routing from declarative field-spec triples instead of quotation-based `dict-get` scaffolding
- final routing to different downstream delegates from the parsed delegate decision
