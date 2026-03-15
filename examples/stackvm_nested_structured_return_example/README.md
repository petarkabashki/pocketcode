# StackVM Nested Structured Return Example

This example shows a StackVM caller/delegate pair where the caller normalizes all payload item titles, the delegate returns a nested YAML decision string, and the caller finalizes from declarative nested field specs instead of embedding `get-in?` logic inline.

Layout:

- `flows` (*.md): registers the caller and VM delegate flows
- `normalize.md`: caller flow that loads the shared workspace stdlib io and normalization modules, hands off, then resumes through the paired nested structured finalize workflow
- `confirm_delegate.md`: VM delegate flow that collects a structured choice from one declarative decision table and returns a nested YAML mapping string to the caller
- `vm/common.vm`: local helper facade that re-exports shared `stdlib.normalize` helpers under `common.*`
- `vm/router.vm`: caller script that binds the caller half of `define-choice-finalize-family` for the full caller-side load, normalization, handoff, YAML resume protocol, nested field projection with defaults, and finalization policy, and calls qualified `common.*` helpers
- `vm/delegate.vm`: delegate script that binds the delegate half of `define-choice-finalize-family`, collects a radio choice, declares nested returned fields as path/value specs, layers them onto a shared base mapping, and emits YAML at the answer boundary

The example demonstrates:

- tool-first normalization of all payload item titles in a StackVM caller through `stdlib.io.read-yaml-file-once`
- shared file-read macros loaded from workspace-root `stdlib.io`
- shared normalization helpers loaded from workspace-root `stdlib.normalize`
- pure data fan-out with `parallel-map` before delegate handoff
- a paired nested structured finalize workflow declared in `vm/common.vm` through `define-choice-finalize-family` and bound with `use-workflow-family` for the full caller-side load, normalization, handoff, returned-decision parsing, nested field projection, and finalization protocol
- nested YAML returned through `last_delegated_result.answer`
- caller-side finalization from declarative nested field-spec triples with explicit defaults
- caller-side final answer construction through `finalize-from`
- default handling when an optional nested field is absent from the returned decision
