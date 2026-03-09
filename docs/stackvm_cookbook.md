# StackVM Cookbook

This page collects small, copyable StackVM snippets for the patterns that recur across the checked-in examples.

Use this together with `markdown_assets.md` for the canonical runtime surface and `stackvm_patterns.md` for the example catalog.

## Route With Exact-Match Cases

Use `switch` when a routing decision is based on exact values such as intents, states, or mode names.

```text
"user_intent" store-get
[
  "billing" [ "plugin.billing_route" handoff ]
  "tech" [ "plugin.tech_route" handoff ]
  "default" [ "plugin.general_route" handoff ]
]
switch
```

`switch` checks exact matches first and only runs the optional `"default"` case when no earlier case matched.

## Route With Declarative Rules

Use `cond` when each route depends on a computed rule instead of a single exact-match value.

```text
[
  [ "severity" store-get "critical" = ] [ "plugin.incident_route" handoff ]
  [ "needs_human" store-get bool> ] [ "plugin.human_route" handoff ]
  [ True ] [ "plugin.self_serve_route" handoff ]
]
cond
```

This reads more like a routing table than nested `if` branches.

## Recover From VM-Level Failures

Use `fallback` when a risky quotation may raise during VM evaluation and you want a local recovery path.

```text
[ drop missing-word ]
[ "Recovered after VM failure" answer ]
fallback
```

`fallback` is not a replacement for tool-result branching. Tool failures still arrive through `last-tool-result` and should normally be handled with `failure?`.

## Fan Out Over Pure Data

Use `parallel-map` when you already have a list value on the stack and each item should run through the same pure quotation concurrently.

```text
"[alpha, beta, gamma]" yaml>
[ "item=" swap concat ]
parallel-map
"results" store-set
```

`parallel-map` is intended for pure data transforms and helper-word pipelines. Child quotations should not perform `tool-request`, `handoff`, `ask-user`, or `answer`.

See `examples/stackvm_parallel_map_plugin/` for a checked-in end-to-end example that reuses a user-defined helper word inside each child VM.
See `examples/stackvm_parallel_tool_map_plugin/` for the same pattern after a tool-loaded YAML payload has been normalized into a list.

## Fold Mapped Results Back Down

Use `reduce` when you already have a list on the stack and want to fold it into a single accumulator value.

```text
"[alpha, beta, gamma]" yaml>
""
[ swap dup empty? [ drop ] [ "; " concat concat ] if ]
reduce
```

`reduce` expects the list first, then the initial accumulator, then a quotation. Each child quotation receives the current accumulator beneath the current item and must leave the next accumulator on top of the stack.

See `examples/stackvm_reduce_plugin/` for a checked-in end-to-end example that combines `parallel-map` and `reduce` in one pure pipeline.
See `examples/stackvm_reduce_tool_plugin/` for the same pattern after a tool-loaded YAML payload has been normalized into a list.
See `examples/stackvm_reduce_numeric_plugin/` for a numeric aggregation variant that folds normalized item values into a total.

## Route From Aggregate Thresholds

Use `cond` after `reduce` when a numeric aggregate should determine which downstream route handles the request.

```text
"[1, 2, 3]" yaml>
0
[ + ]
reduce
dup "normalized.total" shared!? drop
[
  [ "normalized.total" shared@ 10 >= ] [ "plugin.high_route" handoff ]
  [ "normalized.total" shared@ 5 >= ] [ "plugin.review_route" handoff ]
  [ True ] [ "plugin.low_route" handoff ]
]
cond
```

See `examples/stackvm_threshold_router_plugin/` for a checked-in end-to-end example that combines numeric aggregation with declarative threshold routing.

## Load A Tool Result Once

When a flow should call a tool on the first turn and consume its result on the second turn, branch on `last-tool-result none?`.

```text
[
  last-tool-result none?
  [
    "core.read_file"
    "{path: payload.yaml}" yaml>
    tool-request
  ]
  [
    last-tool-result "content" dict-get yaml>
    "payload" store-set
  ]
  if
] "decide" define
```

## Normalize Optional Nested Values

Use `get-in?` and a `none?` branch when a nested field may be missing.

```text
"payload" store-get "meta.source" get-in? dup none?
[ drop "unknown" ]
[ ]
if
dup "normalized.source" shared!? drop
```

This keeps the normalized contract stable even when the source payload is partial.

## Normalize Many Items Before Interaction Or Routing

Use `parallel-map` before `prompt-interaction`, `handoff`, or delegate-return logic when the flow should summarize all payload items instead of only `items.0`.

```text
[ "title" dict-get? dup none? [ drop "untitled" ] [ ] if ] "item-title" define

"payload" store-get "items" dict-get? dup none?
[ drop "[]" yaml> ]
[ ]
if
[ item-title ]
parallel-map
dup "normalized.titles" shared!? drop
", " join
dup "normalized.title" shared!? drop
```

This pattern keeps the downstream contract stable for flows that still expect a single `normalized.title` or `normalized.summary`, while also preserving the full item list in `normalized.titles` for later use.

See `examples/stackvm_buttons_plugin/`, `examples/stackvm_radio_plugin/`, `examples/stackvm_checklist_handoff_plugin/`, and `examples/stackvm_checklist_return_plugin/` for checked-in interaction flows that now follow this pattern.

## Branch On Optional Runtime Keys

Use `shared@` for optional runtime-managed keys such as `last_delegated_result`.

```text
"last_delegated_result" shared@ none?
[ "delegate.agent" handoff ]
[ "last_delegated_result" shared@ "answer" dict-get answer ]
if
```

Do not use `store-get` for this pattern when `none?` matters. `store-get` returns the empty string for missing top-level keys, which is not the same as `None`.

## Surface A Question And Stop

Use `ask-user` when the flow should end by surfacing a question.

```text
"Proceed with deployment?" ask-user
```

The runtime will surface this as `Question: Proceed with deployment?`.

## Prompt For Text And Continue

Use `prompt-user` when the flow should collect text input and keep executing.

```text
"Add a short summary" prompt-user
dup "normalized.summary" shared!? drop
"Summary recorded: " swap concat answer
```

`prompt-user` requires `interaction_handler` or `user_input_handler` in the shared store.

## Prompt For Structured Choices And Continue

Use `prompt-interaction` for `buttons`, `radio`, or `checklist` requests.

```text
"{kind: radio, prompt: Choose mode, options: [{id: fast, label: Fast, value: fast}, {id: safe, label: Safe, value: safe}]}" yaml>
prompt-interaction
dup "normalized.mode" shared!? drop
"Selected mode " swap concat answer
```

`prompt-interaction` pushes the selected scalar for `buttons` and `radio`, and a value list for `checklist`.

## Format Checklist Selections Cleanly

Use `join` instead of `str>` when the selected value is a list.

```text
prompt-interaction
dup "normalized.selected_tools" shared!? drop
", " join
"Selected tools: " swap concat answer
```

This avoids Python-style output such as `['git', 'search']`.

## Hand Off And Return To Caller

Use `pending_handoff_policy` with `return_to_caller: true` when the delegate should return control.

```text
"{return_to_caller: true, context_mode: whole, return_transition: continue}" yaml>
"pending_handoff_policy" store-set
"plugin.delegate" handoff
```

The caller can then read `last_delegated_result` on the next turn.

## Finalize From A Delegate Return

When a delegate returns, the caller usually wants the delegate answer or question.

```text
"last_delegated_result" shared@ "answer" dict-get dup none?
[ drop "Delegate returned without an answer." answer ]
[ "Caller received: " swap concat answer ]
if
```

## Parse A Structured Delegate Return And Route

When the delegate should return a machine-readable decision, have it answer with a YAML mapping string and parse that string in the caller.

```text
"last_delegated_result" shared@ "answer" dict-get dup none?
[ drop "Delegate returned without an answer." answer ]
[
  yaml>
  dup "route" dict-get dup "normalized.final_route" shared!? drop
  swap "note" dict-get dup "normalized.delegate_note" shared!? drop

  "normalized.final_route" shared@ "approve" =
  [ "plugin.approve_route" handoff ]
  [
    "normalized.final_route" shared@ "escalate" =
    [ "plugin.escalate_route" handoff ]
    [ "plugin.review_route" handoff ]
    if
  ]
  if
]
if
```

This pattern is used by `stackvm_structured_return_routing_plugin`.

## Parse A Nested Structured Delegate Return And Route

When the delegate should return a nested machine-readable decision, parse the YAML string in the caller, read nested fields with `get-in?`, and route from the extracted decision.

```text
"last_delegated_result" shared@ "answer" dict-get dup none?
[ drop "Delegate returned without an answer." answer ]
[
  yaml>
  dup "decision.route" get-in? dup none?
  [ drop "review" ]
  [ ]
  if
  dup "normalized.final_route" shared!? drop
  drop

  dup "decision.note" get-in? dup none?
  [ drop "no note" ]
  [ ]
  if
  dup "normalized.delegate_note" shared!? drop
  drop

  "meta.source" get-in? dup none?
  [ drop "unspecified" ]
  [ ]
  if
  dup "normalized.delegate_source" shared!? drop
  drop

  "normalized.final_route" shared@ "approve" =
  [ "plugin.approve_route" handoff ]
  [
    "normalized.final_route" shared@ "escalate" =
    [ "plugin.escalate_route" handoff ]
    [ "plugin.review_route" handoff ]
    if
  ]
  if
]
if
```

This pattern is used by `stackvm_nested_structured_return_routing_plugin`.

## Parse A Structured Delegate Return And Finalize

When the delegate should return a machine-readable decision but the caller should still produce the final answer, parse the delegate answer and compose the output in the caller.

```text
"last_delegated_result" shared@ "answer" dict-get dup none?
[ drop "Delegate returned without an answer." answer ]
[
  yaml>
  dup "mode" dict-get dup "normalized.delegate_mode" shared!? drop
  swap "message" dict-get dup "normalized.delegate_message" shared!? drop

  "finalized: "
  "normalized.summary" shared@ concat
  " | mode=" concat
  "normalized.delegate_mode" shared@ concat
  " | note=" concat
  "normalized.delegate_message" shared@ concat
  answer
]
if
```

This pattern is used by `stackvm_structured_return_finalize_plugin`.

## Parse A Nested Structured Return With Defaults

When the delegate returns nested YAML, parse it once and use `get-in?` for optional nested fields before composing the final answer.

```text
"last_delegated_result" shared@ "answer" dict-get dup none?
[ drop "Delegate returned without an answer." answer ]
[
  yaml>
  dup "decision.mode" get-in? dup none?
  [ drop "unknown" ]
  [ ]
  if
  dup "normalized.delegate_mode" shared!? drop
  drop

  dup "decision.note" get-in? dup none?
  [ drop "no note" ]
  [ ]
  if
  dup "normalized.delegate_note" shared!? drop
  drop

  "meta.source" get-in? dup none?
  [ drop "unspecified" ]
  [ ]
  if
  dup "normalized.delegate_source" shared!? drop
  drop

  "nested finalized: "
  "normalized.summary" shared@ concat
  " | mode=" concat
  "normalized.delegate_mode" shared@ concat
  " | note=" concat
  "normalized.delegate_note" shared@ concat
  " | delegate_source=" concat
  "normalized.delegate_source" shared@ concat
  answer
]
if
```

This pattern is used by `stackvm_nested_structured_return_plugin`.

## Recover Explicitly From Tool Failure

Tool failures remain flow-visible through `last-tool-result`, so branch on `failure?` instead of relying on implicit runtime aborts.

```text
last-tool-result failure?
[ "fallback.agent" handoff ]
[ "primary path succeeded" answer ]
if
```

## Build A Readable Summary Once

Normalize and cache a summary string before later branches use it.

```text
"normalized.title" shared@ " from " concat "normalized.source" shared@ concat
dup "normalized.summary" shared!? drop
```

This keeps later prompts, answers, and handoff decisions shorter and more stable.

## Split Reusable Words Across Modules

Keep parsing and reusable normalization words in `vm/common` and put flow-specific routing in a separate router module.

```text
! vm/common.vm
[ last-tool-result "content" dict-get yaml> ] "payload-data" define

! vm/router.vm
[
  payload-data "payload" store-set
  "payload" store-get "meta.source" get-in? dup none?
  [ drop "unknown" ]
  [ ]
  if
  dup "normalized.source" shared!? drop
] "decide" define
```

This keeps shared parsing helpers stable while letting each flow own its routing logic.

## Route From Checklist Selections

When checklist input should choose a downstream delegate, store the list, format it once, and branch on membership.

```text
prompt-interaction
dup "normalized.selected_actions" shared!? drop
dup "delegate" contains?
[
  dup ", " join dup "normalized.selected_actions_text" shared!? drop
  swap drop drop
  "plugin.delegate_route" handoff
]
[
  dup "approve" contains?
  [
    dup ", " join dup "normalized.selected_actions_text" shared!? drop
    swap drop drop
    "plugin.approve_route" handoff
  ]
  [
    dup ", " join dup "normalized.selected_actions_text" shared!? drop
    swap drop drop
    "plugin.review_route" handoff
  ]
  if
]
if
```

This pattern is used by `stackvm_checklist_handoff_plugin`.

## Chain Interactions Across Stages

Use a caller flow for the first interaction, hand off with `return_to_caller`, let the delegate collect the second interaction, and then finalize back in the caller.

```text
! caller
prompt-interaction
dup "normalized.selected_actions" shared!? drop
dup ", " join dup "normalized.selected_actions_text" shared!? drop
swap drop drop
"{return_to_caller: true, context_mode: whole, return_transition: continue}" yaml>
"pending_handoff_policy" store-set
"plugin.confirm_delegate" handoff

! caller on return
"last_delegated_result" shared@ "answer" dict-get
"pipeline complete: " swap concat answer
```

```text
! delegate
"{kind: radio, prompt: Choose delegate plan, options: [{id: review-first, label: Review First, value: review-first}, {id: delegate-now, label: Delegate Now, value: delegate-now}]}" yaml>
prompt-interaction
"delegate plan " swap concat answer
```

This pattern is used by `stackvm_multistage_pipeline_plugin`.

If the first-stage choice should sometimes skip the delegate entirely, branch before setting `pending_handoff_policy` and finalize directly in the caller for the no-delegate path.

## When To Prefer Checked-In Examples

- Start from `stackvm_buttons_plugin` when you need a single-turn structured interaction.
- Start from `stackvm_radio_plugin` when you need a single selected mode.
- Start from `stackvm_prompt_return_plugin` when a prompted delegate should return to its caller after the caller has normalized any multi-item payload summary it wants the delegate to reference.
- Start from `stackvm_checklist_return_plugin` when a delegate returns a multi-selection decision.
- Start from `stackvm_structured_return_routing_plugin` when a delegate should return a structured YAML decision that the caller will parse and route on.
- Start from `stackvm_nested_structured_return_routing_plugin` when a delegate should return nested YAML and the caller should route from nested returned fields with `get-in?`.
- Start from `stackvm_structured_return_finalize_plugin` when a delegate should return a structured YAML decision that the caller will parse into the final answer after multi-item normalization.
- Start from `stackvm_nested_structured_return_plugin` when a delegate should return nested YAML and the caller should read optional nested fields with `get-in?` before finalizing after multi-item normalization.
- Start from `stackvm_checklist_handoff_plugin` when checklist input should select one of several downstream delegates.
- Start from `stackvm_multistage_pipeline_plugin` when two structured interactions should happen across caller and delegate stages in one run after multi-item normalization.
- Start from `stackvm_nested_router_plugin` when the source data is deep and partially optional.