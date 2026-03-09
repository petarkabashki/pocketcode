# StackVM Patterns

This document groups the checked-in StackVM examples by orchestration pattern so it is easier to find a close starting point when authoring a new VM-backed flow.

Use this together with `markdown_assets.md` for the canonical StackVM surface and `pocketflow_agents.md` for how VM-backed flows fit into the broader runtime.

## Shared Helper Conventions

**For the canonical description of StackVM helper conventions and architectural split, always refer to `stackvm_cookbook.md`.**

Most payload-driven checked-in examples now keep reusable normalization helpers in `vm/common.vm` and reserve `vm/router.vm` for orchestration logic. See `stackvm_cookbook.md` for the definitive list and description of normalization/formatting helpers and the architectural split.

Examples that use this helper style include `stackvm_buttons_plugin`, `stackvm_radio_plugin`, `stackvm_checklist_handoff_plugin`, `stackvm_multistage_pipeline_plugin`, the delegate-return routing/finalize examples, and the plain normalization examples.

Use this convention when the example needs a stable normalized shared-state contract across multiple runtime paths. Keep flow-specific prompting, switching, handoff, and returned-decision parsing in the router instead of pushing those behaviors down into shared helpers.

## Direct Answer

- `examples/stackvm_review_plugin/`
  - Reads a file through `core.read_file`
  - Produces a final answer directly from the tool result
  - Good starting point for tool-first answer flows

- `examples/stackvm_parallel_map_plugin/`
  - Builds a fixed list in the VM
  - Uses `parallel-map` with a user-defined helper word
  - Produces the final answer from the mapped result list
  - Good starting point for pure data fan-out patterns

- `examples/stackvm_parallel_tool_map_plugin/`
  - Reads YAML through a tool
  - Extracts payload items with `dict-get?`
  - Uses `parallel-map` after the tool result is normalized into an in-memory list
  - Good starting point for tool-first fan-out patterns

- `examples/stackvm_reduce_plugin/`
  - Builds a fixed list in the VM
  - Uses `parallel-map` for fan-out and `reduce` for fan-in
  - Produces the final answer from a single accumulated summary string
  - Good starting point for pure map-and-reduce patterns

- `examples/stackvm_reduce_tool_plugin/`
  - Reads YAML through a tool
  - Extracts payload items with `dict-get?`
  - Uses `parallel-map` for fan-out and `reduce` for fan-in after the tool result is normalized into an in-memory list
  - Good starting point for tool-first map-and-reduce patterns

- `examples/stackvm_reduce_numeric_plugin/`
  - Reads YAML through a tool
  - Normalizes numeric item values with `dict-get?` and `int>`
  - Uses `parallel-map` for fan-out and `reduce` to calculate a numeric total
  - Good starting point for numeric aggregation patterns

- `examples/stackvm_tool_normalize_plugin/`
  - Reads YAML through a tool
  - Normalizes all payload item titles with `parallel-map` plus selected fields into shared state
  - Produces the final answer from the normalized view instead of the raw payload

## Direct Handoff

- `examples/stackvm_handoff_plugin/`
  - Minimal StackVM router
  - Hands off immediately to a PocketFlow delegate
  - Good reference for the smallest VM-to-flow handoff seam

## Handoff On Failure

- `examples/stackvm_resilient_plugin/`
  - Calls a tool
  - Branches on `failure?`
  - Hands off to a fallback flow on tool failure

## Config-Driven Routing

- `examples/stackvm_config_router_plugin/`
  - Reads workspace YAML config
  - Uses `bool>`, `int>`, `dict-get?`, and `list-get?`
  - Routes to delegates based on normalized config values

- `examples/stackvm_nested_router_plugin/`
  - Reads nested mixed dict/list YAML config
  - Uses `get-in?`, `list-get?`, and `set-in?`
  - Records nested audit state before handing off

## Aggregate Then Route

- `examples/stackvm_threshold_router_plugin/`
  - Reads YAML through a tool
  - Uses `parallel-map` and `reduce` to calculate a numeric total
  - Uses `cond` to route to different delegates based on threshold bands
  - Good starting point for aggregate-then-route patterns

## Normalize Then Handoff

- `examples/stackvm_normalize_handoff_plugin/`
  - Reads YAML through a tool
  - Normalizes all payload item titles, enabled, and source into `shared["normalized"]`
  - Hands off based on normalized shared-state instead of raw payload structure

## Normalize Then Ask

- `examples/stackvm_normalize_ask_plugin/`
  - Reads YAML through a tool
  - Normalizes all payload item titles plus selected values into shared state
  - Surfaces a user question derived from the normalized view

## Prompt Then Continue

- `examples/stackvm_normalize_confirm_plugin/`
  - Reads YAML through a tool
  - Normalizes all payload item titles plus selected values into shared state
  - Uses `prompt-user` to collect a bridged user reply and continue execution to a final answer

## Structured Interaction Then Continue

- `examples/stackvm_buttons_plugin/`
  - Reads YAML through a tool
  - Normalizes all payload item titles into shared state with `parallel-map`
  - Uses `prompt-interaction` with a buttons request and continues to a final answer based on the selected option

- `examples/stackvm_radio_plugin/`
  - Reads YAML through a tool
  - Normalizes all payload item titles into shared state with `parallel-map`
  - Uses `prompt-interaction` with a radio request and continues to a final answer from the selected mode

These examples share the same authoring pattern: define `item-title` plus reusable `normalize-item-titles`, `store-normalized-source`, `store-normalized-enabled` where needed, and `store-normalized-summary` helpers in `vm/common.vm`, keep the aggregated summary in shared state, and let the structured interaction operate on that stable summary instead of a single raw item.

## Prompted Delegate Return

- `examples/stackvm_prompt_return_plugin/`
  - Uses a StackVM caller to normalize all payload item titles with `parallel-map` and hand off with `return_to_caller`
  - Uses a StackVM delegate to collect a structured button choice through `prompt-interaction`
  - Finalizes back in the caller from `last_delegated_result` after the delegate returns

## Checklist Delegate Return

- `examples/stackvm_checklist_return_plugin/`
  - Uses a StackVM caller to normalize all payload item titles with `parallel-map` and hand off with `return_to_caller`
  - Uses a StackVM delegate to collect a checklist selection through `prompt-interaction`
  - Demonstrates the non-scalar `last_user_value` path flowing through `last_delegated_result`
  - Uses `join` to format the selected values for user-facing output

## Structured Delegate Return Then Route

- `examples/stackvm_structured_return_routing_plugin/`
  - Uses a StackVM caller to normalize all payload item titles with `parallel-map` and hand off with `return_to_caller`
  - Uses a StackVM delegate to collect a structured radio choice and return a YAML mapping string to the caller
  - Parses `last_delegated_result.answer` with `yaml>` in the caller and routes to a final downstream delegate from the returned decision

- `examples/stackvm_nested_structured_return_routing_plugin/`
  - Uses a StackVM caller to normalize all payload item titles with `parallel-map` and hand off with `return_to_caller`
  - Uses a StackVM delegate to return a nested YAML mapping string to the caller
  - Parses `last_delegated_result.answer` with `yaml>` and reads nested route fields through `get-in?` before choosing the final downstream delegate

## Structured Delegate Return Then Finalize

- `examples/stackvm_structured_return_finalize_plugin/`
  - Uses a StackVM caller to normalize all payload item titles with `parallel-map` and hand off with `return_to_caller`
  - Uses a StackVM delegate to collect a structured radio choice and return a YAML mapping string to the caller
  - Parses `last_delegated_result.answer` with `yaml>` in the caller and builds the final answer directly from the returned fields

- `examples/stackvm_nested_structured_return_plugin/`
  - Uses a StackVM caller to normalize all payload item titles with `parallel-map` and hand off with `return_to_caller`
  - Uses a StackVM delegate to return a nested YAML mapping string to the caller
  - Parses `last_delegated_result.answer` with `yaml>` and reads nested fields through `get-in?`, including defaults for missing nested fields

## Checklist Then Handoff

- `examples/stackvm_checklist_handoff_plugin/`
  - Reads YAML through a tool
  - Normalizes all payload item titles into shared state with `parallel-map`
  - Collects checklist actions through `prompt-interaction`
  - Uses a reusable `format-selected-actions` helper to store the joined action text once before handing off to different delegates

Together with `stackvm_buttons_plugin` and `stackvm_radio_plugin`, these checklist examples are the current checked-in references for the recurring “normalize many items, then interact or route from the shared summary” pattern.

## Multi-Stage Pipeline

- `examples/stackvm_multistage_pipeline_plugin/`
  - Reads YAML through a tool and normalizes all payload item titles into shared state in the caller
  - Collects checklist actions in the caller, formats them once with `format-selected-actions`, then hands off with `return_to_caller`
  - Uses a VM delegate to ask a second structured question before returning to the caller
  - Can also finalize directly in the caller when the first-stage selection does not require delegation
  - Finalizes back in the caller from both the checklist summary and `last_delegated_result`

## Choosing A Starting Point

- Start from `stackvm_handoff_plugin` when the VM only decides where work should go next.
- Start from `stackvm_parallel_map_plugin` when the VM should fan out over an in-memory list with a pure quotation and collect the results back into the same flow.
- Start from `stackvm_parallel_tool_map_plugin` when the VM should load a list through a tool first and only then fan out over the normalized in-memory data.
- Start from `stackvm_reduce_plugin` when the VM should fan out over a list and then fold the mapped values back into one final summary or accumulator.
- Start from `stackvm_reduce_tool_plugin` when the VM should load a list through a tool first, then fold the mapped values back into one final summary or accumulator.
- Start from `stackvm_reduce_numeric_plugin` when the VM should load numeric values through a tool and fold them into a total or other numeric aggregate.
- Start from `stackvm_threshold_router_plugin` when the VM should route to a downstream delegate based on a numeric aggregate derived with `parallel-map` and `reduce`.
- Start from `stackvm_tool_normalize_plugin` when the VM should reshape tool data, including all payload item titles, before final output.
- Start from `stackvm_normalize_handoff_plugin` when delegates should consume a stable shared-state contract instead of raw tool payloads.
- Start from `stackvm_normalize_ask_plugin` when the VM should turn normalized state, including multi-item title summaries, into a user-facing question.
- Start from `stackvm_normalize_confirm_plugin` when the VM should collect a bridged text reply and keep executing in the same turn after multi-item normalization.
- Start from `stackvm_buttons_plugin` when the VM should present structured choices and keep executing from the selected option value.
- Start from `stackvm_radio_plugin` when the VM should enforce a single structured choice but keep executing from that selected value.
- Start from `stackvm_prompt_return_plugin` when a VM delegate should collect user input and return a decision to its caller instead of finalizing the overall run directly.
- Start from `stackvm_checklist_return_plugin` when a VM delegate should collect multiple selections and return that decision to its caller.
- Start from `stackvm_structured_return_routing_plugin` when a VM delegate should return a structured YAML decision and the caller should choose the final downstream route from that returned value.
- Start from `stackvm_nested_structured_return_routing_plugin` when a VM delegate should return nested YAML and the caller should choose the final downstream route from nested returned fields.
- Start from `stackvm_structured_return_finalize_plugin` when a VM delegate should return a structured YAML decision and the caller should turn that returned value directly into the final answer.
- Start from `stackvm_nested_structured_return_plugin` when a VM delegate should return nested YAML and the caller should read optional nested fields with `get-in?` before finalizing after multi-item normalization.
- Start from `stackvm_checklist_handoff_plugin` when checklist input should determine which downstream delegate handles the request.
- Start from `stackvm_multistage_pipeline_plugin` when one VM stage should collect the first decision, delegate a second decision, and then finalize back in the original caller after multi-item normalization.
- Start from `stackvm_nested_router_plugin` when the incoming data is deeply nested and partially optional.