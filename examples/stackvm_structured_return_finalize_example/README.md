# StackVM Structured Return Finalize Example

This example shows a StackVM caller/delegate pair where the caller normalizes all payload item titles, the delegate returns a structured YAML decision string, and the caller finalizes from declarative returned-field specs instead of hand-written projection code.

Layout:

- `flows/*.md`: registers the caller and VM delegate flows
- `flows/normalize.md`: caller flow that loads the shared workspace stdlib io and normalization modules, hands off, then resumes through the paired structured finalize workflow
- `flows/confirm_delegate.md`: VM delegate flow that collects a structured choice from one declarative decision table and returns a YAML decision string to the caller
- `vm/common.vm`: local helper facade that re-exports shared `stdlib.normalize` helpers under `common.*`
- `vm/router.vm`: caller script that binds the caller half of `define-choice-finalize-family` for the full caller-side load, normalization, handoff, YAML resume protocol, declarative returned-field projection, and finalization policy, and calls qualified `common.*` helpers
- `vm/delegate.vm`: delegate script that binds the delegate half of `define-choice-finalize-family`, collects a radio choice, declares returned fields as path/value specs, and emits YAML only at the answer boundary

The example demonstrates:

- tool-first normalization of all payload item titles in a StackVM caller through `stdlib.io.read-yaml-file-once`
- shared file-read macros loaded from workspace-root `stdlib.io`
- shared normalization helpers loaded from workspace-root `stdlib.normalize`
- pure data fan-out with `parallel-map` before delegate handoff
- a paired structured finalize workflow declared in `vm/common.vm` through `define-choice-finalize-family` and bound with `use-workflow-family` for the full caller-side load, normalization, handoff, returned-decision parsing, field projection, and finalization protocol
- delegate answers encoded as stable YAML strings instead of free-form text
- caller-side finalization from declarative field-spec triples instead of quotation-based `dict-get` scaffolding
- final answer construction in the caller from returned structured fields through `finalize-from` rather than a downstream route
