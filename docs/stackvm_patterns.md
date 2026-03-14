# StackVM Patterns

This document groups the checked-in StackVM examples by orchestration pattern so it is easier to find a close starting point when authoring a new VM-backed flow.

Use this together with `markdown_assets.md` for the canonical StackVM surface, `stackvm_macros.md` for the macro surface, `stackvm_stdlib.md` for shared reusable VM modules, and `pocketflow_agents.md` for how VM-backed flows fit into the broader runtime.

## Shared Helper Conventions

**For the canonical description of self-contained StackVM authoring, combinators, macros, and when to extract helper modules, always refer to `stackvm_cookbook.md`.**

Most payload-driven checked-in examples can be authored as one self-contained Markdown VM program. When examples extract helpers into `vm/common.vm`, prefer explicit `module` / `export` / `import` linking. Shared helpers that should outlive one namespace now belong under workspace-root `vm/stdlib/`. `vm_module_prefixes` remains supported only for compatibility with older authored flows. See `stackvm_cookbook.md` and `stackvm_stdlib.md` for the current guidance.

Examples that use this helper style include `stackvm_buttons_example`, `stackvm_radio_example`, `stackvm_checklist_handoff_example`, `stackvm_multistage_pipeline_example`, the delegate-return routing/finalize examples, and the plain normalization examples.

Use this convention when the example needs a stable normalized shared-state contract across multiple runtime paths. Keep flow-specific prompting, switching, handoff, and returned-decision parsing in the router instead of pushing those behaviors down into shared helpers.

## Macro Authoring

- `examples/stackvm_macro_authoring_example/`
  - Loads an explicit `vm/common` helper module and calls exported `common.*` words from macros and runtime code
  - Uses a helper word for the repeated YAML request payload
  - Defines user-authored macros with `defmacro` and `syntax-quote`
  - Shows `unquote` and `unquote-splice` in a runnable end-to-end flow
  - Good starting point when built-in macros are close but not quite enough

## Direct Answer

- `examples/stackvm_example/`
  - Reads a file through `core.read_file`
  - Produces a final answer directly from the tool result
  - Good starting point for tool-first answer flows

- `examples/stackvm_parallel_map_example/`
  - Builds a fixed list in the VM
  - Uses `parallel-map` with a user-defined helper word
  - Produces the final answer from the mapped result list
  - Good starting point for pure data fan-out patterns

- `examples/stackvm_parallel_tool_map_example/`
  - Reads YAML through a tool
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Uses `tool-once` for the tool loop
  - Extracts payload items with `dict-get?`
  - Uses `parallel-map` after the tool result is normalized into an in-memory list
  - Good starting point for tool-first fan-out patterns

- `examples/stackvm_reduce_example/`
  - Builds a fixed list in the VM
  - Uses `parallel-map` for fan-out and `reduce` for fan-in
  - Produces the final answer from a single accumulated summary string
  - Good starting point for pure map-and-reduce patterns

- `examples/stackvm_reduce_tool_example/`
  - Reads YAML through a tool
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Uses `tool-once` for the tool loop
  - Extracts payload items with `dict-get?`
  - Uses `parallel-map` for fan-out and `reduce` for fan-in after the tool result is normalized into an in-memory list
  - Good starting point for tool-first map-and-reduce patterns

- `examples/stackvm_reduce_numeric_example/`
  - Reads YAML through a tool
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Uses `tool-once` for the tool loop
  - Normalizes numeric item values with `dict-get?` and `int>`
  - Uses `parallel-map` for fan-out and `reduce` to calculate a numeric total
  - Good starting point for numeric aggregation patterns

- `examples/stackvm_tool_normalize_example/`
  - Reads YAML through a tool
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Uses the built-in `tool-once` macro to keep the request/consume loop compact
  - Normalizes all payload item titles with `parallel-map` plus selected fields into shared state
  - Produces the final answer from the normalized view instead of the raw payload

## Direct Handoff

- `examples/stackvm_handoff_example/`
  - Minimal StackVM router
  - Hands off immediately to a PocketFlow delegate
  - Good reference for the smallest VM-to-flow handoff seam

## Handoff On Failure

- `examples/stackvm_resilient_example/`
  - Calls a tool
  - Branches on `failure?`
  - Hands off to a fallback flow on tool failure

## Config-Driven Routing

- `examples/stackvm_config_router_example/`
  - Reads workspace YAML config
  - Loads the shared workspace-root stdlib module `stdlib.config`
  - Uses explicit module imports instead of compatibility prefixes
  - Uses `schema-apply` to coerce booleans and integers and fill config defaults
  - Uses the built-in `schema-route` macro to store validation errors and route on the normalized config value
  - Uses `match` for the top-level enabled versus disabled routing shape
  - Uses the built-in `indexed-handoff-route` macro for final route selection after normalization and the built-in `shared-handoff` macro for repeated fallback-reason branches
  - Routes to delegates based on normalized config values, uses `shared-handoff` for repeated fallback-reason branches, and falls back on schema-invalid config

- `examples/stackvm_nested_router_example/`
  - Reads nested mixed dict/list YAML config
  - Loads the shared workspace-root stdlib module `stdlib.config`
  - Uses `schema-apply` to normalize nested objects and fill defaults
  - Uses the built-in `schema-route` macro to store validation errors, persist the normalized config once, and route on the validated value
  - Uses `match` for top-level routing and selected-target destructuring
  - Uses the built-in `indexed-handoff-route` macro for final target selection, `set-in?` for the audit update step, and built-in `shared-handoff` plus `maybe-handoff` macros around fallback and final selected-agent handoff behavior
  - Records nested audit state before handing off, uses `shared-handoff` for repeated fallback-reason branches, and falls back on schema-invalid config

## Aggregate Then Route

- `examples/stackvm_threshold_router_example/`
  - Reads YAML through a tool
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Uses `tool-once` for the tool loop
  - Uses `parallel-map` and `reduce` to calculate a numeric total
  - Uses the built-in `handoff-rules` macro to route to different delegates based on threshold bands
  - Good starting point for aggregate-then-route patterns

## Normalize Then Handoff

- `examples/stackvm_normalize_handoff_example/`
  - Reads YAML through a tool
  - Loads shared file-read macros from workspace-root `stdlib.io`
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Uses `stdlib.io.read-yaml-file-once` for the file-loading tool loop
  - Normalizes all payload item titles, enabled, and source into `shared["normalized"]`
  - Hands off based on normalized shared-state instead of raw payload structure

## Normalize Then Ask

- `examples/stackvm_normalize_ask_example/`
  - Reads YAML through a tool
  - Loads shared file-read macros from workspace-root `stdlib.io`
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Uses `stdlib.io.read-yaml-file-once` for the file-loading tool loop
  - Normalizes all payload item titles plus selected values into shared state
  - Uses the built-in `ask-from` macro so both fallback and normalized questions can be composed from quotations instead of inline `ask-user` strings
  - Surfaces a user question derived from the normalized view

## Prompt Then Continue

- `examples/stackvm_normalize_confirm_example/`
  - Reads YAML through a tool
  - Loads shared file-read macros from workspace-root `stdlib.io`
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Uses `stdlib.io.read-yaml-file-once` for the file-loading tool loop
  - Normalizes all payload item titles plus selected values into shared state
  - Uses the built-in `prompt-store-text` macro to collect a bridged text reply, persist it, and continue execution to a final answer

## Structured Interaction Then Continue

- `examples/stackvm_buttons_example/`
  - Reads YAML through a tool
  - Loads shared file-read macros from workspace-root `stdlib.io`
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Declares a direct continuation contract in `vm/common.vm` through `define-choice-continue-spec` and binds it with `use-workflow-spec`
  - Normalizes all payload item titles into shared state with `parallel-map`
  - Presents a buttons request and continues to a final answer based on the selected option

- `examples/stackvm_radio_example/`
  - Reads YAML through a tool
  - Loads shared file-read macros from workspace-root `stdlib.io`
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Declares a direct continuation contract in `vm/common.vm` through `define-choice-continue-spec` and binds it with `use-workflow-spec` for the radio continuation policy

These examples share the same authoring pattern: load reusable normalization helpers from `stdlib.normalize`, keep the aggregated summary in shared state, declare one direct continuation contract in `vm/common.vm` with `define-choice-continue-spec`, and bind that contract from the entry VM file with `use-workflow-spec` rather than repeating inline file-load, normalization, and interaction macros.

## Prompted Delegate Return

- `examples/stackvm_prompt_return_example/`
  - Loads shared file-read macros from workspace-root `stdlib.io`
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Declares one paired answer workflow in `vm/common.vm` through `define-choice-answer-family` and binds it on both the caller and delegate sides with `use-workflow-family`
  - Uses one top-level caller/delegate contract family instead of separate lower-level prompt and return protocol macros

- `examples/stackvm_delegate_return_example/`
  - Loads shared file-read macros from workspace-root `stdlib.io`
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Uses a StackVM caller to normalize all payload item titles with `parallel-map` and hand off with the built-in `return-delegate` macro
  - Declares the delegate-side decision contract in `vm/common.vm` through `define-choice-answer-spec` and binds it with `use-workflow-spec`
  - Uses `return-delegate` to pass `last_delegated_result.answer` straight back through the caller

## Checklist Delegate Return

- `examples/stackvm_checklist_return_example/`
  - Loads shared file-read macros from workspace-root `stdlib.io`
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Declares one paired checklist answer workflow in `vm/common.vm` through `define-choice-answer-family` and binds it on both the caller and delegate sides, with `contains` matching in the delegate policy
  - Demonstrates the non-scalar `last_user_value` path flowing through `last_delegated_result`
  - Uses one top-level caller/delegate contract family instead of separate lower-level answer and prompt macros
  - Uses `join` to format the selected values for user-facing output

## Structured Delegate Return Then Route

- `examples/stackvm_structured_return_routing_example/`
  - Loads shared file-read macros from workspace-root `stdlib.io`
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Declares one paired structured route workflow in `vm/common.vm` through `define-choice-route-family` and binds it on both the caller and delegate sides
  - Uses a StackVM delegate to collect a structured radio choice through that shared contract
  - Declares both sides of the workflow as data contracts: returned field specs in the delegate and resumed route policy in the caller

- `examples/stackvm_nested_structured_return_routing_example/`
  - Loads shared file-read macros from workspace-root `stdlib.io`
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Declares one paired nested structured route workflow in `vm/common.vm` through `define-choice-route-family` and binds it on both the caller and delegate sides
  - Uses a StackVM delegate to collect a structured radio choice through that shared contract and return a nested YAML mapping declared as field specs over a shared base mapping
  - Keeps nested returned-data defaults and resumed route policy visible as one caller/delegate contract family

## Structured Delegate Return Then Finalize

- `examples/stackvm_structured_return_finalize_example/`
  - Loads shared file-read macros from workspace-root `stdlib.io`
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Declares one paired structured finalize workflow in `vm/common.vm` through `define-choice-finalize-family` and binds it on both the caller and delegate sides
  - Uses a StackVM delegate to collect a structured radio choice through that shared contract
  - Declares both the returned field contract and the resumed finalization contract from top-level workflow macros

- `examples/stackvm_nested_structured_return_example/`
  - Loads shared file-read macros from workspace-root `stdlib.io`
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Declares one paired nested structured finalize workflow in `vm/common.vm` through `define-choice-finalize-family` and binds it on both the caller and delegate sides
  - Uses a StackVM delegate to collect a structured radio choice through that shared contract and return a nested YAML mapping declared as field specs over a shared base mapping
  - Keeps nested returned-data defaults and resumed finalization policy visible as one caller/delegate contract family

## Checklist Then Handoff

- `examples/stackvm_checklist_handoff_example/`
  - Reads YAML through a tool
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Declares a checklist continuation contract in `vm/common.vm` through `define-choice-continue-spec` and binds it with `use-workflow-spec`
  - Uses a reusable `format-selected-actions` helper to store the joined action text once before handing off to different delegates

Together with `stackvm_buttons_example` and `stackvm_radio_example`, these checklist examples are the current checked-in references for the recurring “normalize many items, then interact or route from the shared summary” pattern.

## Multi-Stage Pipeline

- `examples/stackvm_multistage_pipeline_example/`
  - Loads shared file-read macros from workspace-root `stdlib.io`
  - Loads shared normalization helpers from workspace-root `stdlib.normalize` through a local `common` facade
  - Reads YAML through a tool and normalizes all payload item titles into shared state in the caller through `define-choice-continue-answer-family`
  - Collects checklist actions in the caller through the same top-level normalized interaction surface, formats them once with `format-selected-actions`, then either hands off with `return_to_caller` or finalizes directly
  - Binds the delegate answer half of `define-choice-continue-answer-family` before returning to the caller
  - Can also finalize directly in the caller when the first-stage selection does not require delegation
  - Uses `stdlib.io.read-yaml-file-once` for the caller file-loading turn and `finalize-from` for both caller-finalized paths
  - Finalizes back in the caller from both the checklist summary and `last_delegated_result`

## Choosing A Starting Point

- Start from `stackvm_handoff_example` when the VM only decides where work should go next.
- Start from `stackvm_parallel_map_example` when the VM should fan out over an in-memory list with a pure quotation and collect the results back into the same flow.
- Start from `stackvm_parallel_tool_map_example` when the VM should load a list through a tool first and only then fan out over the normalized in-memory data.
- Start from `stackvm_reduce_example` when the VM should fan out over a list and then fold the mapped values back into one final summary or accumulator.
- Start from `stackvm_reduce_tool_example` when the VM should load a list through a tool first, then fold the mapped values back into one final summary or accumulator.
- Start from `stackvm_reduce_numeric_example` when the VM should load numeric values through a tool and fold them into a total or other numeric aggregate.
- Start from `stackvm_threshold_router_example` when the VM should route to a downstream delegate based on a numeric aggregate derived with `parallel-map` and `reduce`.
- Start from `stackvm_tool_normalize_example` when the VM should reshape tool data, including all payload item titles, before final output, and you want the canonical `stdlib.io.read-yaml-file-once` pattern.
- Start from `stackvm_normalize_handoff_example` when delegates should consume a stable shared-state contract instead of raw tool payloads.
- Start from `stackvm_normalize_ask_example` when the VM should turn normalized state, including multi-item title summaries, into a user-facing question.
- Start from `stackvm_normalize_confirm_example` when the VM should collect a bridged text reply and keep executing in the same turn after multi-item normalization.
- Start from `stackvm_buttons_example` when the VM should load a payload, normalize it, and then continue from a structured choice through `define-choice-continue-spec`.
- Start from `stackvm_radio_example` when the VM should enforce a single structured choice but keep executing from that selected value without immediately switching on exact-match cases.
- Start from `stackvm_prompt_return_example` when a VM delegate should collect user input and return a decision to its caller instead of finalizing the overall run directly, and both sides should bind the same `define-choice-answer-family`.
- Start from `stackvm_delegate_return_example` when a VM delegate should return the final answer text and the caller should pass that answer through via `return-delegate`.
- Start from `stackvm_checklist_return_example` when a VM delegate should collect multiple selections and return that decision to its caller while both sides bind the same `define-choice-answer-family`.
- Start from `stackvm_structured_return_routing_example` when a VM delegate should return a structured YAML decision and the caller should choose the final downstream route from that returned value through `define-choice-route-family`.
- Start from `stackvm_nested_structured_return_routing_example` when a VM delegate should return nested YAML and the caller should choose the final downstream route from nested returned fields through `define-choice-route-family`.
- Start from `stackvm_structured_return_finalize_example` when a VM delegate should return a structured YAML decision and the caller should turn that returned value directly into the final answer through `define-choice-finalize-family`.
- Start from `stackvm_nested_structured_return_example` when a VM delegate should return nested YAML and the caller should finalize from nested returned fields through declarative field specs after multi-item normalization through `define-choice-finalize-family`.
- Start from `stackvm_checklist_handoff_example` when checklist input should determine which downstream delegate handles the request.
- Start from `stackvm_multistage_pipeline_example` when one VM stage should collect the first decision, delegate a second decision, and then finalize back in the original caller after multi-item normalization through `finalize-from`.
- Start from `stackvm_config_router_example` when routing should come from normalized config and you want a checked-in `schema-apply` plus `match` example.
- Start from `stackvm_nested_router_example` when the incoming data is deeply nested, partially optional, and should be normalized before routing.
- Start from `stackvm_macro_authoring_example` when you need a checked-in reference for user-authored macros layered on top of helper words and built-in macros.
