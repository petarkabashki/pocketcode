# StackVM Cookbook

This page collects small, copyable StackVM snippets for the patterns that recur across the checked-in examples.

Use this together with `markdown_assets.md` for the canonical runtime surface, `stackvm_macros.md` for the compile-time macro surface, and `stackvm_patterns.md` for the example catalog.

## Choose Between Helper Words And Macros

Prefer the smallest mechanism that matches the job:

- use `define` for reusable runtime helpers, especially repeated YAML literals, parsing steps, and shared-state normalization
- use a built-in macro for a recurring authoring pattern that already has a stable expansion, such as `tool-once`, `prompt-route`, `delegate-return`, or `finalize-from`
- use `defmacro` when you need a new postfix authoring surface over ordinary StackVM AST

If the repeated part is mostly data, especially a YAML literal, keep it in a helper word. If the repeated part is mostly control-flow shape, prefer a macro.

## Guard A Branch With `when`

Use `when` when the flow only needs a truthy branch and an empty false branch would be noise.

```text
"normalized.enabled" shared@
[ "Enabled summary ready." answer ]
when
```

`when` expands to the same `if` shape the runtime already understands, but it keeps the happy-path branch compact.

## Guard A Branch With `unless`

Use `unless` when the negative case is the one worth naming.

```text
"normalized.enabled" shared@
[ "Payload is disabled." answer ]
unless
```

This is the same control-flow surface as `when`, just with the condition negated during expansion.

## Read A Shared Value With A Default

Use `shared-or` when the flow wants `shared@` semantics plus a fallback value and you do not want to repeat the `dup none?` branch.

```text
"normalized.source" "unknown" shared-or
"Source: " swap concat answer
```

`shared-or` is for optional runtime-managed values. It is not a replacement for nested dict or list traversal inside payload data.

## Route With Exact-Match Cases

Use `switch` when a routing decision is based on exact values such as intents, states, or mode names.

```text
"user_intent" store-get
[
  "billing" [ "router.billing_route" handoff ]
  "tech" [ "router.tech_route" handoff ]
  "default" [ "router.general_route" handoff ]
]
switch
```

`switch` checks exact matches first and only runs the optional `"default"` case when no earlier case matched.

## Route With Declarative Rules

Use `cond` when each route depends on a computed rule instead of a single exact-match value.

```text
[
  [ "severity" store-get "critical" = ] [ "router.incident_route" handoff ]
  [ "needs_human" store-get bool> ] [ "router.human_route" handoff ]
  [ True ] [ "router.self_serve_route" handoff ]
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

`parallel-map` is intended for pure data transforms and helper-word pipelines. Each child receives a cloned snapshot of the parent shared store, so any `shared!` or `store-set` mutation inside the child is discarded when the child finishes. Child quotations should not perform `tool-request`, `handoff`, `ask-user`, or `answer`.

See `examples/stackvm_parallel_map_example/` for a checked-in end-to-end example that reuses a user-defined helper word inside each child VM.
See `examples/stackvm_parallel_tool_map_example/` for the same pattern after a tool-loaded YAML payload has been normalized into a list.

## Fold Mapped Results Back Down

Use `reduce` when you already have a list on the stack and want to fold it into a single accumulator value.

```text
"[alpha, beta, gamma]" yaml>
""
[ swap dup empty? [ drop ] [ "; " concat concat ] if ]
reduce
```

`reduce` expects the list first, then the initial accumulator, then a quotation. Each child quotation receives the current accumulator beneath the current item and must leave the next accumulator on top of the stack. Like `parallel-map`, each reducer step runs with a cloned shared-store snapshot, so reducer-local `shared!` or `store-set` changes do not leak back to the parent flow.

See `examples/stackvm_reduce_example/` for a checked-in end-to-end example that combines `parallel-map` and `reduce` in one pure pipeline.
See `examples/stackvm_reduce_tool_example/` for the same pattern after a tool-loaded YAML payload has been normalized into a list.
See `examples/stackvm_reduce_numeric_example/` for a numeric aggregation variant that folds normalized item values into a total.

## Route From Aggregate Thresholds

Use `cond` after `reduce` when a numeric aggregate should determine which downstream route handles the request.

```text
"[1, 2, 3]" yaml>
0
[ + ]
reduce
dup "normalized.total" shared!? drop
[
  [ "normalized.total" shared@ 10 >= ] [ "router.high_route" handoff ]
  [ "normalized.total" shared@ 5 >= ] [ "router.review_route" handoff ]
  [ True ] [ "router.low_route" handoff ]
]
cond
```

See `examples/stackvm_threshold_router_example/` for a checked-in end-to-end example that combines numeric aggregation with declarative threshold routing.

## Load A Tool Result Once

Prefer the built-in `tool-once` macro when a flow should call a tool on the first turn and consume its result on the second turn.

```text
[
  "core.read_file"
  [ "{path: payload.yaml}" yaml> ]
  [
    last-tool-result failure?
    [ "Could not load the payload." answer ]
    [
      last-tool-result "content" dict-get yaml>
      "payload" store-set
    ]
    if
  ]
  tool-once
] "decide" define
```

`tool-once` expands to the same `last-tool-result none?` pattern the runtime already understands, but it keeps the router focused on the later-turn logic instead of repeating the request branch in every tool-first example.

When a flow still uses the manual `last-tool-result none? ... tool-request ... if` pattern, runtime metadata now records a non-fatal `manual-tool-loop` authoring warning in `last_vm_validation_warnings`.

## Define A Simple Custom Macro

Use `defmacro` when a local project pattern is not covered by the built-in macro set.

```text
[ value ]
[ [ value unquote ] "Macro says: " swap concat answer ]
syntax-quote "answer-with-prefix" defmacro

"hello" answer-with-prefix
```

This keeps the call site short while still expanding to ordinary executable StackVM before runtime. For the full compile-time surface, including `gensym`, refer to `stackvm_macros.md`.

## Splice A Quotation Into Expanded Code

Use `unquote-splice` when a macro should inline a quotation body into surrounding generated code rather than leave the quotation intact as one nested node.

```text
[ body ]
[ [ body unquote-splice ] answer ]
syntax-quote "answer-from" defmacro

"hello"
[ "Result: " swap concat ]
answer-from
```

This pattern is useful when you want a compact macro for “run these steps, then answer” or similar wrapper shapes.

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

[
  "items" dict-get? dup none?
  [ drop "[]" yaml> ]
  [ ]
  if
  [ item-title ]
  parallel-map
  dup "normalized.titles" shared!? drop
  ", " join
  dup "normalized.title" shared!? drop
] "normalize-item-titles" define

"payload" store-get normalize-item-titles
```

In the checked-in examples, `item-title`, `normalize-item-titles`, `store-normalized-source`, `store-normalized-enabled` where needed, and `store-normalized-summary` often live in `vm/common.vm` so multiple flows can reuse the same normalization helpers without repeating payload shaping.

The checked-in examples now pair `normalize-item-titles` with a reusable `store-normalized-summary` helper so routers can build `normalized.summary` without repeating the title-plus-source concatenation logic.

This pattern keeps the downstream contract stable for flows that still expect a single `normalized.title` or `normalized.summary`, while also preserving the full item list in `normalized.titles` for later use.

See `examples/stackvm_buttons_example/`, `examples/stackvm_radio_example/`, `examples/stackvm_checklist_handoff_example/`, and `examples/stackvm_checklist_return_example/` for checked-in interaction flows that now follow this pattern.

## Reusable VM Modules

Start with one self-contained Markdown VM program. Extract `vm/common.vm` or other helper modules only when multiple programs genuinely share the same contract.

- Keep data-shaping helpers in `vm/common.vm` when multiple flows in the example family need the same normalization contract.
- Keep routing, prompting, delegate return handling, and final answer composition in the self-contained Markdown file until the control-flow shape itself is worth extracting.
- Treat helper words as contract builders for the `shared["normalized"]` store, not as places to trigger runtime transitions.

The current helper set used across the checked-in examples is:

- `normalize-item-titles`: map every payload item to a safe title, store `normalized.titles`, and store the joined `normalized.title`.
- `store-normalized-source`: read `meta.source` from the payload, default to `unknown`, and store `normalized.source`.
- `store-normalized-enabled`: read `items.0.enabled`, default to `false`, normalize with `bool>`, and store `normalized.enabled` in the boolean-gated examples.
- `store-normalized-summary`: compose `normalized.title` plus `normalized.source`, store `normalized.summary`, and leave the summary on the stack when the caller wants to use it immediately.
- `format-selected-actions`: join a checklist selection, store `normalized.selected_actions_text`, and leave both the original list and formatted text available for routing.

Use these helpers when the router would otherwise repeat the same payload normalization steps before every interaction or handoff path. Do not move delegate-return parsing helpers into this pattern unless the returned payload shape is also shared across multiple flows.

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

`prompt-user` requires `interaction_handler` in the shared store.

## Prompt For Structured Choices And Continue

Use `prompt-route` when a structured interaction should immediately branch into exact-match cases. `prompt-interaction` is still available directly when the flow needs to keep the raw selected value on the stack for additional work before routing.

```text
[
  "{kind: radio, prompt: Choose mode, options: [{id: fast, label: Fast, value: fast}, {id: safe, label: Safe, value: safe}]}" yaml>
]
[
  "fast" [ "Selected mode fast" answer ]
  "default" [ "Selected mode safe" answer ]
]
prompt-route
```

`prompt-route` expands to `prompt-interaction` plus `switch`. The request expression and case table are passed as quotations, so multi-step setup such as `dict-set` or `shared!?` can stay inside the macro arguments.

When a flow still uses direct `prompt-interaction ... switch` exact-match routing, runtime metadata now records a non-fatal `manual-prompt-route` authoring warning in `last_vm_validation_warnings`.

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
"router.delegate" handoff
```

The caller can then read `last_delegated_result` on the next turn.

## Pass A Delegate Answer Straight Through

Use `delegate-return` when the caller should hand off with `return_to_caller` and then answer directly from a returned path without any extra caller-side formatting.

```text
"{return_to_caller: true, context_mode: whole, return_transition: continue}" yaml>
"pending_handoff_policy" store-set
"router.delegate"
"last_delegated_result.answer"
delegate-return
```

`delegate-return` does not set the return policy automatically, so the `pending_handoff_policy` setup stays explicit in the caller. See `examples/stackvm_delegate_return_example/` for the checked-in end-to-end reference.

## Finalize From A Delegate Return

When a delegate returns and the caller should still compose the final answer, prefer `finalize-from` around the caller-side formatting or parsing logic.

```text
"last_delegated_result" shared@ "answer" dict-get dup none?
[ drop "Delegate returned without an answer." answer ]
[ [ "Caller received: " swap concat ] finalize-from ]
if
```

`finalize-from` keeps the returned-value shaping inside a quotation and leaves the outer branch focused on the missing-result fallback.

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
  [ "router.approve_route" handoff ]
  [
    "normalized.final_route" shared@ "escalate" =
    [ "router.escalate_route" handoff ]
    [ "router.review_route" handoff ]
    if
  ]
  if
]
if
```

This pattern is used by `stackvm_structured_return_routing_example`.

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
  [ "router.approve_route" handoff ]
  [
    "normalized.final_route" shared@ "escalate" =
    [ "router.escalate_route" handoff ]
    [ "router.review_route" handoff ]
    if
  ]
  if
]
if
```

This pattern is used by `stackvm_nested_structured_return_routing_example`.

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

This pattern is used by `stackvm_structured_return_finalize_example`.

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

This pattern is used by `stackvm_nested_structured_return_example`.

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
format-selected-actions
over "delegate" contains?
[
  swap drop drop
  "router.delegate_route" handoff
]
[
  over "approve" contains?
  [
    swap drop drop
    "router.approve_route" handoff
  ]
  [
    swap drop drop
    "router.review_route" handoff
  ]
  if
]
if
```

In the checked-in checklist examples, `format-selected-actions` lives in `vm/common.vm` and both stores `normalized.selected_actions_text` and leaves the original list plus formatted text on the stack so routing can branch on membership without recomputing the joined string.

This pattern is used by `stackvm_checklist_handoff_example`.

## Chain Interactions Across Stages

Use a caller flow for the first interaction, hand off with `return_to_caller`, let the delegate collect the second interaction, and then finalize back in the caller.

```text
! caller
"core.read_file"
[ "{path: payload.yaml}" yaml> ]
[
  prompt-interaction
  dup "normalized.selected_actions" shared!? drop
  dup ", " join dup "normalized.selected_actions_text" shared!? drop
  swap drop drop
  "{return_to_caller: true, context_mode: whole, return_transition: continue}" yaml>
  "pending_handoff_policy" store-set
  "router.confirm_delegate" handoff
]
tool-once

! caller on return
[ 
  "last_delegated_result" shared@ "answer" dict-get
  "pipeline complete: " swap concat
] finalize-from
```

```text
! caller direct-finalize branch
[
  "pipeline complete: "
  "normalized.summary" shared@ concat
  " | actions=" concat
  "normalized.selected_actions_text" shared@ concat
  " | delegate=skipped" concat
] finalize-from
```

```text
! delegate
"{kind: radio, prompt: Choose delegate plan, options: [{id: review-first, label: Review First, value: review-first}, {id: delegate-now, label: Delegate Now, value: delegate-now}]}" yaml>
prompt-interaction
"delegate plan " swap concat answer
```

This pattern is used by `stackvm_multistage_pipeline_example`.

If the first-stage choice should sometimes skip the delegate entirely, branch before setting `pending_handoff_policy` and use `finalize-from` directly in the caller for the no-delegate path.

## When To Prefer Checked-In Examples

- Start from `stackvm_buttons_example` when you need a single-turn structured interaction.
- Start from `stackvm_radio_example` when you need a single selected mode.
- Start from `stackvm_prompt_return_example` when a prompted delegate should return to its caller after the caller has normalized any multi-item payload summary it wants the delegate to reference.
- Start from `stackvm_checklist_return_example` when a delegate returns a multi-selection decision.
- Start from `stackvm_structured_return_routing_example` when a delegate should return a structured YAML decision that the caller will parse and route on.
- Start from `stackvm_nested_structured_return_routing_example` when a delegate should return nested YAML and the caller should route from nested returned fields with `get-in?`.
- Start from `stackvm_structured_return_finalize_example` when a delegate should return a structured YAML decision that the caller will parse into the final answer after multi-item normalization.
- Start from `stackvm_nested_structured_return_example` when a delegate should return nested YAML and the caller should read optional nested fields with `get-in?` before finalizing after multi-item normalization.
- Start from `stackvm_checklist_handoff_example` when checklist input should select one of several downstream delegates.
- Start from `stackvm_multistage_pipeline_example` when two structured interactions should happen across caller and delegate stages in one run after multi-item normalization.
- Start from `stackvm_nested_router_example` when the source data is deep and partially optional.
