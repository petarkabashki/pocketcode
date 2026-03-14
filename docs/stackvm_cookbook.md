# StackVM Cookbook

This page collects small, copyable StackVM snippets for the patterns that recur across the checked-in examples.

Use this together with `markdown_assets.md` for the canonical runtime surface, `stackvm_macros.md` for the compile-time macro surface, `stackvm_patterns.md` for the example catalog, and `stackvm_stdlib.md` for the checked-in reusable module surface.

For a forward-looking implementation plan, see `stackvm_roadmap.md`. That roadmap is a proposal document, not a description of current runtime behavior.

## Embed A Reusable Standalone Runtime

Use `StackVmStandaloneRuntime` when the same portable StackVM program should be invoked repeatedly from Python without recompiling or re-wiring the host contract every time.

```python
from pocketcode.core.stackvm_driver import (
    build_stackvm_standalone_host_config,
    create_stackvm_standalone_runtime_target,
)

host_config = build_stackvm_standalone_host_config(
    tool_runtime=tool_runtime,
    interaction_handler=interaction_handler,
    llm_router=llm_router,
    system_prompt="Standalone system prompt",
)

runtime = create_stackvm_standalone_runtime_target(
    vm_entry="router.main",
    vm_modules=["stdlib.io", "vm/router"],
    base_dir=workspace_root / "example_ns",
    search_roots=[workspace_root],
    workspace_root=workspace_root,
    agent_name="demo.runtime",
    host_config=host_config,
    shared_store_seed={"mode": "embedded"},
)

first = runtime.run(request="hello")
second = runtime.run(request="again", debug=True)
```

The runtime object keeps one compiled program, one default host config, one workspace root, and one seed shared store. Each `run(...)` call starts from a fresh shallow copy of that seed state and still accepts per-run overrides for request text, debug mode, host hooks, and additional shared-store values.

## Embed A Persistent Standalone Session

Use `StackVmStandaloneSession` when repeated calls should intentionally carry forward shared state and a simple transcript instead of starting from a fresh seed each time.

```python
from pocketcode.core.stackvm_driver import (
    create_stackvm_standalone_runtime,
    create_stackvm_standalone_session,
)

runtime = create_stackvm_standalone_runtime(
    compiled=compiled_program,
    workspace_root=workspace_root,
    agent_name="demo.session",
)

session = create_stackvm_standalone_session(
    runtime=runtime,
    title="Demo Session",
)

first = session.run(request="hello")
second = session.run(request="again")
```

The current session layer persists two things between runs:

- curated shared-store state from the previous result, excluding known run-scoped wiring and trace fields
- a simple transcript of user and assistant turns

Each session run injects that transcript back into shared state as:

- `standalone_transcript`
- `standalone_transcript_text`

That makes the transcript available to portable StackVM programs through ordinary shared-state reads such as `"standalone_transcript_text" shared@`. This is separate from PocketCoder's saved-session system. Standalone sessions do not use `_session_manager`, `active_session_id`, or the PocketCoder-only `active-session-transcript` host words.

Standalone sessions now also support a portable snapshot boundary:

```python
snapshot = session.snapshot()
restored = restore_stackvm_standalone_session(
    runtime=runtime,
    snapshot=snapshot,
)
```

Use `restore_stackvm_standalone_session_target(...)` when the program should be rebuilt from loader fields at restore time instead of reusing an already-created runtime.

## Choose Between Helper Words And Macros

Prefer the smallest mechanism that matches the job:

- use `define` for reusable runtime helpers, especially repeated YAML literals, parsing steps, and shared-state normalization
- use a built-in macro for a recurring authoring pattern that already has a stable expansion, such as `tool-once`, `prompt-route`, `delegate-return`, or `finalize-from`
- use `defmacro` when you need a new postfix authoring surface over ordinary StackVM AST

Prefer explicit StackVM modules with `module`, `export`, and `import` when helpers are meant to be reused across files. Keep `vm_module_prefixes` for compatibility with older helper modules that still rely on automatic qualification. When a helper should be reused across multiple namespaces, place it under workspace-root `vm/stdlib/` instead of copying it into each flow namespace, and load it by its manifest-backed package name such as `stdlib.io` or `stdlib.normalize`.

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

## Match Structured Values

Use `match` when the branch decision depends on structured data and you want a single pattern table instead of repeated `dict-get?`, `get-in?`, and `if` chains.

```text
"{kind: approve, payload: {id: 7, tags: [fast, safe]}}" yaml>
[
  [ "{kind: approve, payload: {id: $approval_id, tags: [$first_tag, $second_tag]}}" yaml> ]
  [
    "match.approval_id" shared@ "approval_id" store-set
    "match.first_tag" shared@ "first_tag" store-set
    "match.second_tag" shared@ "second_tag" store-set
  ]
  _
  [ "fallback" "route" store-set ]
]
match
```

Current `match` semantics:

- patterns may be literals, the wildcard `_`, or quotations that leave a pattern value
- pattern values may recursively destructure dicts and lists
- strings that begin with `$`, such as `"$approval_id"`, bind the matched value
- strings of the form `"$approval_id:int"` only bind when the matched value has the requested type; supported type names are `any`, `none`, `bool`, `int`, `float`, `number`, `str`, `list`, and `dict`
- list patterns may end with `$*name` to bind the remaining tail of a variable-length list
- dict patterns may include the special key `$rest` to bind unmatched remaining keys from the input mapping
- repeated bindings must stay consistent; a later `$name` only matches when it equals the value captured earlier in the same pattern
- successful bindings are stored under `match.<name>` and in the mapping `match`
- if no pattern matches and there is no wildcard case, `match` leaves no additional stack output and simply continues

The current implementation is intentionally pragmatic. It is best suited to YAML-shaped routing and normalization cases where a small set of fields should be validated, tail-captured, and bound for later steps without dropping back to repeated `dict-get?`, `list-get?`, and `get-in?` plumbing.

## Validate And Coerce Structured Data

Use `schema-check` when a flow should validate a YAML-shaped value against a simple schema and inspect the errors without rewriting the value.

Use `schema-apply` when the flow should also coerce primitive values and fill in declared defaults.

```text
"{count: \"7\", enabled: yes}" yaml>
"{type: object, required: [count, enabled], properties: {count: {type: integer}, enabled: {type: boolean}, label: {type: string, default: normalized}}}" yaml>
schema-apply
"result" store-set
```

Both words return a mapping with this shape:

- `success`: `True` when no schema errors were found
- `value`: the original value for `schema-check`, or the coerced/defaulted value for `schema-apply`
- `errors`: a list of human-readable validation failures

Current schema support intentionally matches the small schema subset already used elsewhere in the repo:

- `type`
- `properties`
- `required`
- `items`
- `default`
- `enum`

Supported primitive schema types are `string`, `boolean`, `integer`, and `number`. The current coercion path is intended for config-style YAML and form-like inputs, not arbitrary lossy conversions.

See `examples/stackvm_config_router_example/` and `examples/stackvm_nested_router_example/` for checked-in end-to-end flows that use `schema-apply` to normalize workspace YAML before routing with `match`.

## Validate Then Match

Use `validated-match` when a flow already has a `{success, value, errors}` envelope from `schema-check` or `schema-apply` and the next step is “run one setup quotation, then `match` on `value`, otherwise run an invalid branch”.

```text
schema-apply
[
  [ dup "value" dict-get? dup "config" store-set drop ]
  [
    [ "{enabled: true, route: $target}" yaml> ] [ "match.target" shared@ handoff ]
    [ "{enabled: false}" yaml> ] [ "fallback.agent" handoff ]
    _
    [ "invalid" "route_reason" shared! "fallback.agent" handoff ]
  ]
  [ drop "invalid" "route_reason" shared! "fallback.agent" handoff ]
  validated-match
]
```

Use a no-op `result_expr` quotation such as `[ ]` when the setup step does not need to persist anything from the envelope before matching. This is the current shorthand used by the checked-in config-router examples to avoid repeating the schema-envelope `if` branch around every `match` table.

## Store Errors Then Route

Use `schema-route` when a flow already has a schema envelope on the stack and the repeated pattern is:

- store `errors` into shared state
- optionally store the validated `value` once for later steps
- route on the normalized `value`
- run one invalid fallback branch when validation failed

```text
schema-apply
"config_errors"
"config"
[
  [ "{enabled: true, route: $target}" yaml> ] [ "match.target" shared@ handoff ]
  [ "{enabled: false}" yaml> ] [ "fallback.agent" handoff ]
  _
  [ "invalid" "route_reason" shared! "fallback.agent" handoff ]
]
[ drop "invalid" "route_reason" shared! "fallback.agent" handoff ]
schema-route
```

Pass `None` as `value_store_path` when the validated value does not need to be kept for later mutation or lookup. The checked-in config and nested-router examples now use `schema-route` as the canonical higher-level form over `schema-apply`, `validated-match`, and `match`.

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

## Route By Rule Table And Handoff

Use `handoff-rules` when the flow wants a declarative rule table whose successful branch should always:

- store one route label or band in shared state
- hand off to a downstream agent

```text
[
  [ "normalized.total" shared@ 10 >= ] "high" "router.high_route"
  [ "normalized.total" shared@ 5 >= ] "review" "router.review_route"
  [ True ] "low" "router.low_route"
]
"normalized.band"
handoff-rules
```

`handoff-rules` is the higher-level shorthand for a `cond` table where every action branch repeats the same `band_path shared! ... handoff` shape. The checked-in threshold router example now uses this form after `parallel-map` plus `reduce`.

## Route One Key Through Handoff Branches

Use `handoff-switch` when a flow already has or can compute one route key and the repeated pattern is:

- evaluate a small route expression once
- map route values to delegate agents
- hand off from every branch

```text
[ "normalized.final_route" shared@ ]
[
  "approve" "router.approve_route"
  "escalate" "router.escalate_route"
  "default" "router.review_route"
]
handoff-switch
```

`handoff-switch` is now the canonical shorthand for caller-side structured-return routing flows that used to repeat `switch` action quotations or nested `if` chains where every successful branch only performed `handoff`.

## Project Values Into Shared State

Use `project-shared` when a flow has one mapping on the stack and the repeated pattern is:

- evaluate several extraction quotations against that same source value
- store each projected result into shared state once
- continue into routing or finalization logic after those shared values exist

```text
[
  [ "route" dict-get ] "normalized.final_route"
  [ "note" dict-get ] "normalized.delegate_note"
]
[
  "normalized.final_route" shared@
  [
    "approve" [ "router.approve_route" handoff ]
    "default" [ "router.review_route" handoff ]
  ] switch
]
project-shared
```

Each projection quotation is evaluated against the same original source value, so this is also a good fit for nested reads and defaulting logic:

```text
[
  [ "decision.mode" get-in? dup none? [ drop "unknown" ] [ ] if ] "normalized.delegate_mode"
  [ "meta.source" get-in? dup none? [ drop "unspecified" ] [ ] if ] "normalized.delegate_source"
]
[
  "normalized.delegate_mode" shared@ answer
]
project-shared
```

`project-shared` is now the canonical caller-side shorthand for structured-return flows that used to repeat several `dict-get`, `get-in?`, and `shared!?` storage lines before routing or finalization. Because the body continues inline after the projected writes, caller-finalized flows should keep `finalize-from` inside the body quotation rather than placing it after `project-shared`, and `finalize-from` still expects its own quoted value expression inside that body.

## Project Returned Fields From Declarative Specs

Use `project-fields` when a caller flow has one parsed returned mapping on the stack and the repeated pattern is:

- describe selected returned fields as `source_path shared_path default` triples
- store each resolved value into shared state once
- continue into routing or finalization logic without hand-writing `dict-get` or `get-in?` quotations

```text
[
  "decision.route" "normalized.final_route" "review"
  "decision.note" "normalized.delegate_note" "no note"
  "meta.source" "normalized.delegate_source" "delegate"
]
[
  "normalized.final_route" shared@ answer
]
project-fields
```

`project-fields` is the stronger authored surface above `project-shared` for structured-return callers. It keeps the returned-field contract visible as data instead of burying it inside projection quotations.

## Recover From VM-Level Failures

Use `fallback` when a risky quotation may raise during VM evaluation and you want a local recovery path.

```text
[ drop missing-word ]
[ "Recovered after VM failure" answer ]
fallback
```

`fallback` is not a replacement for tool-result branching. Tool failures still arrive through `last-tool-result` and should normally be handled with `failure?`.

`fallback` now recovers ordinary VM execution failures such as missing words or bad data operations, but it does not swallow illegal child-effect violations raised from combinators such as `parallel-map` or `reduce`.

At the runtime boundary, host words still populate the familiar shared-store keys such as `final_answer`, `question_to_ask`, `pending_handoff_agent`, and `pending_tool`, but they now do so through the PocketCoder host adapter in `pocketcode/core/stackvm_host.py` instead of writing those fields directly inside each host word. The VM also emits typed effect metadata through `last_vm_effect` and appends each VM turn to both `vm_effect_history` and the broader `runtime_effect_history`. The agent runtime prefers that effect metadata when deciding what happens next, and `last_vm_transition` is now just the derived string view of the same effect.

Current analysis also classifies runtime words by host surface:

- `core`: ordinary language words with no host dependency
- `portable_host`: host words that fit the current lightweight standalone script surface, such as `answer`, `ask-user`, `prompt-user`, `prompt-interaction`, `tool-call`, `llm-call`, `transition`, `request`, `system-prompt`, `llm-profile`, `tool-definitions`, `last-tool-result`, `last-tool-route`, and `results`
- `pocketcoder_host`: PocketCoder-specific orchestration words such as `tool-request`, `handoff`, and session-oriented readers such as `active-session-transcript`

`/stackvm inspect`, `/stackvm check`, and `/stackvm explain` now report `host_surfaces_used`, `pocketcoder_host_words_used`, and `standalone_script_compatible` from the static analysis payload so it is clear why a script can or cannot use the lightweight standalone adapter.

## Fan Out Over Pure Data

Use `parallel-map` when you already have a list value on the stack and each item should run through the same pure quotation concurrently.

```text
"[alpha, beta, gamma]" yaml>
[ "item=" swap concat ]
parallel-map
"results" store-set
```

`parallel-map` is intended for pure data transforms and helper-word pipelines. Each child receives a cloned snapshot of the parent shared store, so any `shared!` or `store-set` mutation inside the child is discarded when the child finishes. Child quotations must not perform runtime effects such as `tool-request`, `handoff`, `ask-user`, or `answer`; those now raise a dedicated illegal child-effect runtime error.

See `examples/stackvm_parallel_map_example/` for a checked-in end-to-end example that reuses a user-defined helper word inside each child VM.
See `examples/stackvm_parallel_tool_map_example/` for the same pattern after a tool-loaded YAML payload has been normalized into a list.

## Shape Collections Without Parallelism

Use `map`, `flat-map`, `filter`, `find`, `any?`, `all?`, `sort-by`, and `group-by` when the flow is primarily reshaping in-memory data and does not need concurrent fan-out.

```text
"[1, 2, 3, 4]" yaml>
[ 10 * ]
map
"mapped" store-set

"[[1], [2, 3], []]" yaml>
[ ]
flat-map
"flattened" store-set

"[1, 2, 3, 4]" yaml>
[ 2 > ]
filter
"filtered" store-set

"[{name: gamma, score: 3}, {name: alpha, score: 1}, {name: beta, score: 2}]" yaml>
[ "score" dict-get ]
sort-by
"sorted" store-set

"[{kind: a, value: 1}, {kind: b, value: 2}, {kind: a, value: 3}]" yaml>
[ "kind" dict-get ]
group-by
"grouped" store-set

"[1, 2, 3, 4]" yaml>
[ 2 > ]
find
"first_match" store-set
```

These words use the same child-quotation safety rule as `parallel-map` and `reduce`: each child quotation runs in an isolated child VM, any child `shared!` or `store-set` mutation is discarded, and runtime transition words such as `tool-request`, `handoff`, `ask-user`, and `answer` are illegal inside the child quotation.

- `map` returns a new list of child results
- `flat-map` returns a new list and flattens child results that are themselves lists or tuples by one level
- `filter` returns a new list containing the original items whose predicate result was truthy
- `find` returns the first original item whose predicate result was truthy, or `none`
- `any?` returns `True` when any predicate result was truthy
- `all?` returns `True` only when every predicate result was truthy
- `sort-by` returns a new list ordered by the child quotation result for each item
- `group-by` returns a new mapping from child quotation result to the list of original items in that group

Use `merge` when two mappings should be combined immutably with right-hand keys overriding left-hand keys.

```text
"{left: 1, shared: old}" yaml>
"{right: 2, shared: new}" yaml>
merge
"merged" store-set
```

## Fold Mapped Results Back Down

Use `reduce` when you already have a list on the stack and want to fold it into a single accumulator value.

```text
"[alpha, beta, gamma]" yaml>
""
[ swap dup empty? [ drop ] [ "; " concat concat ] if ]
reduce
```

`reduce` expects the list first, then the initial accumulator, then a quotation. Each child quotation receives the current accumulator beneath the current item and must leave the next accumulator on top of the stack. Like `parallel-map`, each reducer step runs with a cloned shared-store snapshot, so reducer-local `shared!` or `store-set` changes do not leak back to the parent flow. Child quotations must remain effect-free in the same way as `parallel-map`.

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

When the tool-first shape is specifically “read a workspace file through `core.read_file`, parse YAML, then continue”, prefer the shared `stdlib.io` macro layer instead of repeating the request expression in every router:

```text
"payload.yaml"
[
  last-tool-result failure?
  [ "Could not load the payload." answer ]
  [
    last-tool-result "content" dict-get yaml>
    "payload" store-set
  ]
  if
]
stdlib.io.read-yaml-file-once
```

The checked-in normalize, interaction, and config-router examples now use `stdlib.io.read-yaml-file-once` as the shared file-loading authoring surface over the built-in `tool-once` macro.

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

When those helpers are loaded through `vm_module_prefixes`, the caller module should reference them with their qualified names, for example `common.normalize-item-titles` and `common.store-normalized-source`.

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

`prompt-user` requires `interaction_handler` in the shared store. That callback-backed behavior is now part of the portable standalone host surface too, so standalone scripts can use `prompt-user` when the embedding host supplies the same handler.

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

`prompt-interaction` uses the same `interaction_handler` requirement as `prompt-user`, and that handler-backed behavior is also available through the portable standalone host surface.

## Prompt, Store, And Continue

Use `prompt-store` when a structured interaction should:

- present a request built at runtime
- store the selected value in shared state once
- continue executing from that same selected value

```text
[
  "{kind: radio, prompt: Choose mode, options: [{id: delegate, label: Delegate, value: delegate}]}" yaml>
]
"normalized.mode"
[ "Selected mode " swap concat answer ]
prompt-store
```

`prompt-store` is the direct-interaction counterpart to `prompt-route`. It keeps the selected value on the stack for follow-up formatting or branching while still making the shared-store persistence explicit and reusable.

For direct authored choice tables and return workflows, prefer the specialized choice-workflow builders first: `define-choice-continue-spec` for direct normalized continuation, `define-choice-answer-spec` for a single delegate answer contract, `define-choice-answer-family` for paired caller/delegate answer workflows, `define-choice-continue-answer-family` for hybrid router/delegate pipelines, `define-choice-route-family` for structured resumed routing, and `define-choice-finalize-family` for structured resumed finalization. Keep `define-workflow-family` plus `use-workflow-family` as the generic compile-time family layer, `define-workflow-spec` plus `use-workflow-spec` as the generic single-policy layer, inline `workflow-spec` plus `continue-workflow-contract`, `answer-workflow-contract`, `route-workflow-contract`, and `finalize-workflow-contract` as lower-level contract adapters, `summary-choice-flow` when only the normalized-summary prompt needs abstraction, `normalized-choice-router` when the run still wants one generic normalized direct-router macro, and plain `choice-flow` when the prompt logic is fully custom. `choice-policy`, `choice-contract`, `choice-decision`, and `choice-structured-decision` remain available as lower-level escape hatches. `stdlib.prompt` remains available when multiple flows intentionally share the same request shape.

## Normalize One Loaded Payload

Use `normalize-loaded-payload` when a flow already has the checked-in payload mapping on the stack and should apply the standard StackVM normalization contract once.

```text
normalize-loaded-payload
```

`normalize-loaded-payload` is the current shorthand for the repeated example-local sequence of:

- loading `common.payload-data`
- normalizing item titles
- storing the normalized source
- storing the aggregated `normalized.summary`

It is the normalization bridge underneath both `normalized-choice-router` and `normalized-return-flow`.

## Continue From A Normalized Summary Choice

Use `summary-choice-flow` when normalized state is already present and the next step should:

- derive prompt text from a static prefix plus `normalized.summary`
- declare a choice table directly
- either continue in the current router or answer/emit structured output in a delegate

```text
"continue"
"buttons"
"Choose next step for "
"normalized.choice"
[
  "approve" "Approve" "approve"
  "review" "Review" "review"
]
[ ]
"exact"
[ ]
[ ]
[
  "approve" [ "Approved " "normalized.summary" shared@ concat answer ]
  "default" [ "Review " "normalized.summary" shared@ concat answer ]
]
summary-choice-flow
```

`summary-choice-flow` is now the preferred generic normalized interaction surface when you still want one macro that can serve both direct routers and delegates.

## Continue From One Declared Choice Spec

Use `define-choice-continue-spec` in `vm/common.vm` plus `use-workflow-spec` in the router when a direct router should:

- load YAML from one payload file
- apply the standard checked-in normalization contract
- derive prompt text from `normalized.summary`
- continue from a declarative choice table

```text
"buttons-workflow"
"payload.yaml"
"buttons"
"Choose next step for "
"normalized.choice"
[
  "approve" "Approve" "approve"
  "review" "Review" "review"
]
[ ]
"exact"
[ ]
[
  "approve" [ "approved " "normalized.summary" shared@ concat answer ]
  "default" [ "review " "normalized.summary" shared@ concat answer ]
]
define-choice-continue-spec
```

The checked-in buttons, radio, and checklist-handoff examples now use `define-choice-continue-spec` as the preferred top-level direct-router authored surface. Keep `define-workflow-spec` plus `use-workflow-spec`, inline `workflow-spec`, `continue-workflow-contract`, and `router-continue-workflow` as lower-level generic forms.

## Load, Normalize, Then Continue Through One Choice Router

Use `normalized-choice-router` when a direct router should:

- load YAML from one payload file
- apply the standard checked-in normalization contract
- derive prompt text from `normalized.summary`
- continue from a declarative choice table

```text
"payload.yaml"
"continue"
"radio"
"Choose route for "
"normalized.route"
[
  "approve" "Approve" "approve"
  "review" "Review" "review"
]
[ ]
"exact"
[ ]
[ ]
[
  "approve" [ "approved " "normalized.summary" shared@ concat answer ]
  "default" [ "review " "normalized.summary" shared@ concat answer ]
]
normalized-choice-router
```

`normalized-choice-router` is now the lower-level normalized direct-router surface under `router-continue-workflow`.

## Ask From Computed Text

Use `ask-from` when the flow should end by surfacing a question, but that question needs multi-step formatting first.

```text
[ "Proceed with " "normalized.summary" shared@ concat "?" concat ]
ask-from
```

`ask-from` is the higher-level shorthand for the common `quotation call ask-user` shape. The checked-in normalize-ask example now uses it for both the fallback question and the normalized follow-up question.

## Prompt For Text, Store, And Continue

Use `prompt-store-text` when a flow should:

- build a text prompt at runtime
- collect a bridged text response with `prompt-user`
- store that response in shared state once
- continue executing from that same text value

```text
[ "Proceed with " "normalized.summary" shared@ concat "?" concat ]
"normalized.reply"
[ bool> ]
prompt-store-text
```

`prompt-store-text` is the text-input counterpart to `prompt-store`. The checked-in normalize-confirm example now uses it to persist the reply before converting it to a boolean confirmation branch.

## Collect A Structured Choice, Store It, And Switch

Use `prompt-store-switch` when a flow needs to:

- build a structured interaction request
- collect one selected value
- store that value in shared state
- route immediately from an exact-value case table

```text
[
  common.radio-delegate-approve-deny
  dup "prompt" "Choose next step for " "normalized.summary" shared@ concat dict-set
]
"normalized.choice"
[
  "approve" [ "router.approve_route" handoff ]
  "default" [ "router.review_route" handoff ]
]
prompt-store-switch
```

`prompt-store-switch` is now the shorthand for direct structured-choice flows that used to stack `prompt-interaction`, `shared!?`, and a hand-written `switch`.

## Collect A Structured Choice And Route Through One Prompt Policy Surface

Use `prompt-store-policy` when one example family wants a single authoring form for:

- exact-match structured routing such as buttons or radio choices
- checklist membership routing after one preparation step
- one persisted shared-store copy of the selected value in both cases

```text
[
  common.buttons-approve-delegate-deny
  dup "prompt" "Choose next step for " "normalized.summary" shared@ concat dict-set
]
"normalized.choice"
"exact"
[ ]
[
  "approve" [ "router.approve_route" handoff ]
  "default" [ "router.review_route" handoff ]
]
prompt-store-policy
```

```text
[
  common.checklist-approve-delegate-review
  dup "prompt" "Choose actions for " "normalized.summary" shared@ concat dict-set
]
"normalized.selected_actions"
"contains"
[ common.format-selected-actions ]
[
  "delegate" [ "router.delegate_route" handoff ]
  "default" [ "router.review_route" handoff ]
]
prompt-store-policy
```

`prompt-store-policy` is the current lower-level request-aware surface above `prompt-store-switch` and `prompt-store-contains-switch`. Prefer the specialized choice-workflow builders for checked-in direct continuation and delegate workflows, `summary-choice-flow` when only the normalized-summary prompt needs abstraction, and only fall back to `prompt-store-policy` when the request mapping already exists.

## Collect A Structured Choice And Declare The Output Contract

Use `prompt-decision` when a delegate flow should:

- build a structured interaction request
- persist the selected value in shared state
- optionally run one preparation step
- choose whether the result should be:
  - a plain returned answer
  - a YAML mapping/list built from data
  - a merged nested YAML mapping with shared metadata

```text
 "answer"
[
  common.buttons-approve-reject
  dup "prompt" "Choose delegate action for " "normalized.summary" shared@ concat dict-set
]
"normalized.delegate_choice"
"exact"
[ ]
[ ]
[
  "approve" [ "delegate approved " "normalized.summary" shared@ concat ]
  "default" [ "delegate rejected " "normalized.summary" shared@ concat ]
]
prompt-decision
```

```text
 "yaml-merge"
[
  common.radio-approve-escalate-review
  dup "prompt" "Choose nested route for " "normalized.summary" shared@ concat dict-set
]
"normalized.delegate_choice"
"exact"
[ ]
[ "{}" yaml> "delegate" "meta.source" set-in ]
[
  "approve" [ "{}" yaml> "approve" "decision.route" set-in "approved by delegate" "decision.note" set-in ]
  "default" [ "{}" yaml> "review" "decision.route" set-in ]
]
prompt-decision
```

`prompt-decision` is the lower-level delegate-side request-aware surface. Prefer `define-choice-answer-spec`, `define-choice-answer-family`, `define-choice-continue-answer-family`, `define-choice-route-family`, and `define-choice-finalize-family` for the checked-in plain-answer and structured delegate families, `summary-choice-flow` when you still want one generic normalized delegate macro, and keep `choice-decision` and `choice-structured-decision` as lower-level specializations.

## Collect A Structured Choice And Return YAML From Mapping Data

Use `prompt-return-yaml-policy` when a delegate should:

- build a structured interaction request
- persist the selected value in shared state
- optionally run one preparation step
- build a mapping or list as ordinary StackVM data
- serialize that value through `yaml<` only at the answer boundary

```text
[
  common.radio-approve-escalate-review
  dup "prompt" "Choose final route for " "normalized.summary" shared@ concat dict-set
]
"normalized.delegate_choice"
"exact"
[ ]
[
  "approve" [ "{}" yaml> "approve" "route" dict-set "approved by delegate" "note" dict-set ]
  "default" [ "{}" yaml> "review" "route" dict-set "review requested by delegate" "note" dict-set ]
]
prompt-return-yaml-policy
```

`prompt-return-yaml-policy` is the lower-level delegate-side surface when the returned value should be machine-readable and the VM should operate on structured mappings instead of hand-authored YAML strings. Prefer `define-choice-route-family` or `define-choice-finalize-family` for the checked-in normalized delegate family, `summary-choice-flow` in `structured` mode when you still want one generic normalized delegate macro, or plain `choice-flow` in `structured` mode when the request itself should still be declared from a fully custom choice table.

## Collect A Structured Choice And Merge Shared YAML Metadata

Use `prompt-return-merge-policy` when a delegate should:

- build a structured interaction request
- persist the selected value in shared state
- optionally run one preparation step
- build a decision-specific mapping
- merge that mapping with shared returned metadata before serializing once through `yaml<`

```text
[
  common.radio-approve-escalate-review
  dup "prompt" "Choose nested route for " "normalized.summary" shared@ concat dict-set
]
"normalized.delegate_choice"
"exact"
[ ]
[ "{}" yaml> "delegate" "meta.source" set-in ]
[
  "approve" [ "{}" yaml> "approve" "decision.route" set-in "approved by delegate" "decision.note" set-in ]
  "default" [ "{}" yaml> "review" "decision.route" set-in ]
]
prompt-return-merge-policy
```

`prompt-return-merge-policy` is the lower-level delegate-side surface when all returned decisions share a common metadata envelope and only the decision fragment changes per branch. Prefer `define-choice-route-family` or `define-choice-finalize-family` for the checked-in normalized delegate family, `summary-choice-flow` in `structured` mode when you still want one generic normalized delegate macro, or plain `choice-flow` in `structured` mode when the request itself should still be declared from a fully custom choice table.

## Build Returned Mappings From Declarative Field Specs

Use `record-fields` when a delegate should:

- start from one base mapping quotation
- declare returned fields as `path value` pairs
- produce the final returned mapping without hand-writing `dict-set` or `set-in` chains

```text
[ "{}" yaml> "delegate" "meta.source" set-in ]
[
  "decision.route" "approve"
  "decision.note" "approved by delegate"
]
record-fields
```

`record-fields` is the current delegate-side counterpart to caller-side `project-fields`. It keeps returned-data contracts visible as tables instead of imperative mapping updates.

## Collect A Structured Choice And Emit A Structured Decision Contract

Use `choice-structured-decision` when a delegate should:

- declare its interaction request from a choice table
- persist the selected value in shared state
- optionally run one preparation step
- start from one base mapping quotation
- describe each returned decision branch as `path value` field specs
- emit YAML at the answer boundary

```text
"radio"
[ "Choose nested route for " "normalized.summary" shared@ concat ]
"normalized.delegate_choice"
[
  "approve" "Approve" "approve"
  "review" "Review" "review"
]
[ ]
"exact"
[ ]
[ "{}" yaml> "delegate" "meta.source" set-in ]
[
  "approve" [ "decision.route" "approve" "decision.note" "approved by delegate" ]
  "default" [ "decision.route" "review" ]
]
choice-structured-decision
```

`choice-structured-decision` is now the lower-level delegate-side structured specialization underneath inline `workflow-spec`, named workflow-spec bindings, the lower-level workflow contracts, `summary-choice-flow`, and `choice-flow`. Prefer `define-choice-route-family` or `define-choice-finalize-family` for the checked-in normalized delegate family, `summary-choice-flow` when you still want one generic normalized delegate macro, and plain `choice-flow` only when the prompt logic is still fully custom.

## Load, Normalize, Hand Off, Then Resume From One Return Contract

Use `normalized-return-flow` when a caller should:

- load YAML from one payload file
- apply the standard checked-in normalization contract
- hand off through the standard return-to-caller path
- resume through either plain answer finalization or field-spec routing/finalization

```text
"answer"
"payload.yaml"
"confirm_delegate"
[ "Delegate did not return a result." answer ]
[ ]
[ "Confirmed " "normalized.summary" shared@ concat " via " swap concat ]
[ ]
normalized-return-flow
```

`normalized-return-flow` is now the preferred generic normalized caller-side surface when you still want one macro that can cover answer, route, and finalize workflows.

## Resume An Answer Workflow Spec

Use `define-choice-answer-family` plus `use-workflow-family` when a caller should load, normalize, hand off, and then finalize from a plain returned answer.

```text
"answer-family"
"payload.yaml"
"confirm_delegate"
[ "Delegate did not return a result." answer ]
[ "Confirmed " swap concat ]
"buttons"
"Choose decision for "
"normalized.choice"
[
  "approve" "Approve" "approve"
  "reject" "Reject" "reject"
]
[ ]
"exact"
[ ]
[
  "approve" [ "approved" ]
  "default" [ "rejected" ]
]
define-choice-answer-family
```

## Resume A Route Workflow Spec

Use `define-choice-route-family` plus `use-workflow-family` when a caller should load, normalize, hand off, parse a structured returned decision, and route from projected fields.

```text
"route-family"
"payload.yaml"
"confirm_delegate"
[ "Delegate did not return a result." answer ]
[
  "route" "normalized.route" None
]
[ "normalized.route" shared@ ]
[
  "approve" "router.approve"
  "default" "router.review"
]
"radio"
"Choose route for "
"normalized.choice"
[
  "approve" "Approve" "approve"
  "review" "Review" "review"
]
[ ]
"exact"
[ ]
[ "{}" yaml> ]
[
  "approve" [ "route" "approve" ]
  "default" [ "route" "review" ]
]
define-choice-route-family
```

## Resume A Finalize Workflow Spec

Use `define-choice-finalize-family` plus `use-workflow-family` when a caller should load, normalize, hand off, parse a structured returned decision, and finalize from projected fields.

```text
"finalize-family"
"payload.yaml"
"confirm_delegate"
[ "Delegate did not return a result." answer ]
[
  "mode" "normalized.mode" None
]
[
  "mode=" "normalized.mode" shared@ concat
]
"radio"
"Choose mode for "
"normalized.choice"
[
  "concise" "Concise" "concise"
  "blocked" "Blocked" "blocked"
]
[ ]
"exact"
[ ]
[ "{}" yaml> ]
[
  "concise" [ "mode" "concise" ]
  "default" [ "mode" "blocked" ]
]
define-choice-finalize-family
```

## Share Contract Blueprints Across Flows

When multiple example families share identical routing options, match modes, and branch rules but differ in their prompts or delegate targets, wrap the choice builder in a parameterized `defmacro` blueprint.

```text
[ name payload_file delegate_target prompt_prefix ]
[
  [ name unquote ]
  [ payload_file unquote ]
  [ delegate_target unquote ]
  [ [ drop "Delegate missing." answer ] ]
  [ [ "Caller received: " swap concat ] ]
  "buttons"
  [ prompt_prefix unquote ]
  "normalized.choice"
  [
    "approve" "Approve" "approve"
    "reject" "Reject" "reject"
  ]
  [ ]
  "exact"
  [ ]
  [
    "approve" [ "approved" ]
    "default" [ "rejected" ]
  ]
  define-choice-answer-family
] syntax-quote "define-approve-reject-blueprint" defmacro

"my-answer-flow" "payload.yaml" "router.delegate" "Choose action for " define-approve-reject-blueprint
```

This keeps `vm/common.vm` focused purely on flow-specific parameters while extracting the structural boilerplate into reusable templates. For cross-namespace reuse, place these blueprints in a shared module like `vm/stdlib/workflows.vm` and import them.

The specialized choice-workflow builders are now the preferred caller/delegate surface for the checked-in prompt-return, checklist-return, multistage, and structured-return examples. Use `define-choice-answer-family`, `define-choice-continue-answer-family`, `define-choice-route-family`, and `define-choice-finalize-family` before falling back to generic workflow families. Keep named workflow specs for single-policy direct or delegate-only cases, inline `workflow-spec`, the lower-level workflow-contract macros, plus `caller-answer-workflow`, `caller-route-workflow`, and `caller-finalize-workflow` as role-specialized forms, or fall back to `normalized-return-flow` and `return-contract-flow` when you still need one generic caller-side return macro.

## Collect A Checklist, Prepare Derived Text, And Route By Membership

Use `prompt-store-contains-switch` when a flow needs to:

- build a checklist interaction request
- collect a selected list
- store that list in shared state
- run one preparation step such as `format-selected-actions`
- route from prioritized membership checks instead of exact-value switching

```text
[
  common.checklist-approve-delegate-review
  dup "prompt" "Choose actions for " "normalized.summary" shared@ concat dict-set
]
"normalized.selected_actions"
[ common.format-selected-actions ]
[
  "delegate" [ "router.delegate_route" handoff ]
  "approve" [ "router.approve_route" handoff ]
  "default" [ "router.review_route" handoff ]
]
prompt-store-contains-switch
```

`prompt-store-contains-switch` is the checklist counterpart to `prompt-store-switch`. It keeps the selected list in shared state, lets one preparation quotation derive reusable text or metadata, and then routes by membership in priority order.

## Call A Tool Directly And Continue

Use `tool-call` when the flow should synchronously invoke a tool and keep the tool result on the stack in the same VM turn.

```text
"resource_root.pocketcode.echo"
"{text: ping}" yaml>
tool-call
"text" dict-get
answer
```

`tool-call` uses the current tool runtime immediately, records `last_tool_result`, `last_tool_route`, and `tool_history`, and keeps executing after pushing the tool result. This is the portable host-surface alternative to transition-based `tool-request`.

Keep using `tool-request` when the flow intentionally wants PocketCoder's orchestration loop and next-turn tool result routing behavior.

## Call The LLM Directly And Continue

Use `llm-call` when the flow should synchronously invoke the selected LLM profile and keep the response on the stack in the same VM turn.

```text
"Summarize the request in one line." llm-call answer
```

`llm-call` is now part of the portable host surface. In standalone script execution it uses the configured engine LLM router directly and still records usage totals and runtime events.

For embedded non-engine callers, the same portable host surface is available through `pocketcode/core/stackvm_driver.py`.

Use:

- `run_stackvm_program(...)` for one-shot raw source strings
- `compile_stackvm_program(...)` plus `run_compiled_stackvm_program(...)` when the embedder wants to cache one compiled raw-source program
- `compile_stackvm_program_target(...)` and `run_stackvm_program_target(...)` when the embedder wants the same `vm_source` / `vm_module` / `vm_modules` / `vm_file` loading semantics that StackVM flows and CLI scripts already use

Prefer `StackVmStandaloneHostConfig(...)` when embedding the standalone runtime. It groups:

- `interaction_handler`
- `runtime_event_handler`
- `llm_router`
- `tool_runtime`
- `llm_profile`
- `system_prompt`
- `tool_definitions`
- `auto_confirm_tools`

into one explicit portable-host contract, while the older loose kwargs remain supported as per-call overrides.

Prefer `build_stackvm_standalone_host_config(...)` when you already have a tool runtime. It derives `tool_definitions` from `tool_runtime.describe_tools(...)` automatically, so most embedders do not need to populate both fields manually.

That target-oriented driver path now resolves shared modules from workspace-root `vm/stdlib/` too, so external callers can run the same module-based StackVM programs without going through `PocketCodeEngine`.

## Format Checklist Selections Cleanly

Use `join` instead of `str>` when the selected value is a list.

```text
prompt-interaction
dup "normalized.selected_tools" shared!? drop
", " join
"Selected tools: " swap concat answer
```

This avoids Python-style output such as `['git', 'search']`.

## Persist A Reason And Hand Off

Use `shared-handoff` when a branch only needs to:

- write one shared value such as a route reason or status
- immediately hand off to a delegate

```text
"missing_route" "route_reason" "router.fallback" shared-handoff
```

This is now the canonical shorthand for config-router fallback branches that used to repeat `value path shared! agent handoff`.

## Hand Off And Return To Caller

Use `return-handoff` when the delegate should return control with the standard checked-in return policy.

```text
"router.delegate" return-handoff
```

`return-handoff` is the current shorthand for the standard `pending_handoff_policy` setup used across the checked-in return-to-caller examples. The caller can then read `last_delegated_result` on the next turn.

## Resume A Return-To-Caller Flow From One Policy

Use `return-flow` when a caller flow should:

- load and normalize an initial payload
- hand off once with the standard return policy
- resume from one quoted caller-side policy when the delegate returns

```text
"prompt_return_payload.yaml"
[
  common.payload-data "payload" store-set
  "payload" store-get common.normalize-item-titles
  "payload" store-get common.store-normalized-source
  common.store-normalized-summary
]
"router.confirm_delegate"
[
  [ drop "Delegate returned without an answer." answer ]
  [ "Caller received delegate decision: " swap concat ]
  returned-answer-policy
]
return-flow
```

`return-flow` is the higher-level caller-side protocol surface above the repeated `last_delegated_result` branch, `stdlib.io.read-yaml-file-once`, generic file-load failure handling, and `return-handoff`.

## Resume And Finalize A Plain Delegate Return In One Step

Use `return-answer-flow` when a caller flow should:

- load and normalize an initial payload
- hand off once with the standard return policy
- handle the missing delegate-answer branch once
- finalize directly from one composed returned-answer expression

```text
"prompt_return_payload.yaml"
[
  common.payload-data "payload" store-set
  "payload" store-get common.normalize-item-titles
  "payload" store-get common.store-normalized-source
  common.store-normalized-summary
]
"router.confirm_delegate"
[ drop "Delegate returned without an answer." answer ]
[ "Caller received delegate decision: " swap concat ]
return-answer-flow
```

`return-answer-flow` is the higher-level shorthand above `return-flow` plus `returned-answer-policy` for plain prompt-return and checklist-return caller flows.

## Pass A Delegate Answer Straight Through

Use `return-delegate` when the caller should use the standard return policy and then answer directly from a returned path without any extra caller-side formatting.

```text
"router.delegate"
"last_delegated_result.answer"
return-delegate
```

Use raw `delegate-return` only when the caller needs a custom return policy instead of the checked-in standard return contract. See `examples/stackvm_delegate_return_example/` for the checked-in end-to-end reference.

## Handoff From An Optional Agent

Use `maybe-handoff` when a flow computes one candidate agent and the repeated pattern is:

- evaluate an expression that may return an agent or `None`
- run a fallback branch when the agent is missing
- otherwise hand off directly

```text
[ "routes" store-get "selected_index" store-get list-get? ]
[ "missing_route" "route_reason" shared! "router.fallback" handoff ]
maybe-handoff
```

`maybe-handoff` is now the shorthand for config-driven routing branches that used to repeat `dup none? [ drop ...fallback... ] [ handoff ] if`.

## Select An Indexed Value Once

Use `indexed-value` when a flow needs to:

- compute a list and an index separately
- select one element with `list-get?`
- run a missing branch when the index does not resolve
- continue with the selected value otherwise

```text
[ "routes" store-get ]
[ "selected_index" store-get ]
[ "missing_route" "route_reason" "router.fallback" shared-handoff ]
[ handoff ]
indexed-value
```

`indexed-value` is now the shorthand for config-router branches that used to repeat `list-get? dup none? [ drop ... ] [ ... ] if` around selected routes or targets.

## Select And Route By Indexed Target

Use `indexed-handoff-route` when a flow needs to:

- compute a list and an index separately
- treat a missing indexed target as a `route_reason`
- hand off to one fallback agent when the index does not resolve
- otherwise continue with the selected target

```text
[ "routes" store-get ]
[ "selected_index" store-get ]
"missing_route"
"router.fallback"
[ handoff ]
indexed-handoff-route
```

`indexed-handoff-route` is now the higher-level shorthand for config-router branches that combine `indexed-value` with the standard fallback-reason handoff contract.

## Parse, Project, And Route A Returned Decision

Use `returned-handoff-switch` when a caller flow needs to:

- handle the missing delegate-answer branch once
- parse one returned YAML decision
- persist selected returned fields into shared state
- route to delegates from one route expression and a handoff-only case table

```text
[ "Delegate returned without an answer." answer ]
[
  [ "route" dict-get ] "normalized.final_route"
  [ "note" dict-get ] "normalized.delegate_note"
]
[ "normalized.final_route" shared@ ]
[
  "approve" "router.approve_route"
  "default" "router.review_route"
]
returned-handoff-switch
```

`returned-handoff-switch` is now the shorthand for the structured-return caller routers that used to stack `returned-yaml`, `project-shared`, and `handoff-switch`.

## Parse, Project, And Finalize A Returned Decision

Use `returned-finalize` when a caller flow needs to:

- handle the missing delegate-answer branch once
- parse one returned YAML decision
- persist selected returned fields into shared state
- finalize from one composed value expression

```text
[ "Delegate returned without an answer." answer ]
[
  [ "mode" dict-get ] "normalized.delegate_mode"
  [ "message" dict-get ] "normalized.delegate_message"
]
[ "finalized: " "normalized.delegate_mode" shared@ concat ]
returned-finalize
```

`returned-finalize` is now the shorthand for the structured-return caller-finalize examples that used to stack `returned-yaml`, `project-shared`, and `finalize-from`.

## Use One Structured Return Policy Surface

Use `returned-policy` when one example family wants one caller-side form for both:

- parsing a returned YAML decision and routing to another delegate
- parsing a returned YAML decision and finalizing directly in the caller

```text
[ "Delegate returned without an answer." answer ]
[
  [ "route" dict-get ] "normalized.final_route"
  [ "note" dict-get ] "normalized.delegate_note"
]
"handoff"
[ "normalized.final_route" shared@ ]
[
  "approve" "router.approve_route"
  "default" "router.review_route"
]
returned-policy
```

```text
[ "Delegate returned without an answer." answer ]
[
  [ "mode" dict-get ] "normalized.delegate_mode"
  [ "message" dict-get ] "normalized.delegate_message"
]
"finalize"
[ "finalized: " "normalized.delegate_mode" shared@ concat ]
[ ]
returned-policy
```

`returned-policy` is the higher-level family surface above `returned-handoff-switch` and `returned-finalize`. Use it when a set of caller flows should share one structured-return contract even if some of them route and others finalize.

## Resume And Apply A Structured Returned Policy In One Step

Use `return-policy-flow` when a caller flow should:

- load and normalize an initial payload
- hand off once with the standard return policy
- handle the missing delegate-answer branch once
- parse a structured returned decision and then either route or finalize from one caller-side policy table

```text
"structured_return_payload.yaml"
[
  common.payload-data "payload" store-set
  "payload" store-get common.normalize-item-titles
  "payload" store-get common.store-normalized-source
  common.store-normalized-summary
]
"router.confirm_delegate"
[ "Delegate returned without an answer." answer ]
[
  [ "route" dict-get ] "normalized.final_route"
  [ "note" dict-get ] "normalized.delegate_note"
]
"handoff"
[ "normalized.final_route" shared@ ]
[
  "approve" "router.approve_route"
  "default" "router.review_route"
]
return-policy-flow
```

`return-policy-flow` is the higher-level shorthand above `return-flow` plus `returned-policy` for structured-return caller flows.

## Resume And Route From Declarative Returned Fields

Use `return-field-route-flow` when a caller flow should:

- load and normalize an initial payload
- hand off once with the standard return policy
- handle the missing delegate-answer branch once
- parse a structured returned decision
- project returned fields from `source_path shared_path default` triples
- route to the next delegate from one caller-side route expression and handoff case table

```text
"structured_return_payload.yaml"
[
  common.payload-data "payload" store-set
  "payload" store-get common.normalize-item-titles
  "payload" store-get common.store-normalized-source
  common.store-normalized-summary
]
"router.confirm_delegate"
[ "Delegate returned without an answer." answer ]
[
  "route" "normalized.final_route" None
  "note" "normalized.delegate_note" None
]
[ "normalized.final_route" shared@ ]
[
  "approve" "router.approve_route"
  "default" "router.review_route"
]
return-field-route-flow
```

`return-field-route-flow` is now the preferred caller-side structured-routing form for the checked-in examples. Use the lower-level `return-policy-flow` only when the returned-field projection contract itself needs custom quotations.

## Resume And Finalize From Declarative Returned Fields

Use `return-field-finalize-flow` when a caller flow should:

- load and normalize an initial payload
- hand off once with the standard return policy
- handle the missing delegate-answer branch once
- parse a structured returned decision
- project returned fields from `source_path shared_path default` triples
- finalize directly from one caller-side value expression

```text
"structured_finalize_payload.yaml"
[
  common.payload-data "payload" store-set
  "payload" store-get common.normalize-item-titles
  "payload" store-get common.store-normalized-source
  common.store-normalized-summary
]
"router.confirm_delegate"
[ "Delegate returned without an answer." answer ]
[
  "mode" "normalized.delegate_mode" None
  "message" "normalized.delegate_message" None
]
[
  "finalized: "
  "normalized.delegate_mode" shared@ concat
]
return-field-finalize-flow
```

`return-field-finalize-flow` is now the preferred caller-side structured-finalization form for the checked-in examples. It keeps the returned-data schema compact and visible without reintroducing quotation-heavy projection code.

## Finalize From A Delegate Return

When a delegate returns and the caller should still compose the final answer from a plain returned value, prefer `returned-answer` together with `finalize-from`.

```text
[ drop "Delegate returned without an answer." answer ]
[ [ "Caller received: " swap concat ] finalize-from ]
returned-answer
```

`returned-answer` keeps the missing-result fallback outside the returned-value formatting logic, and `finalize-from` keeps the returned-value shaping inside a quotation.

## Use One Plain Returned-Answer Policy Surface

Use `returned-answer-policy` when a caller should:

- handle the missing delegate-answer branch once
- format a plain returned value
- finalize directly from that composed value

```text
[ drop "Delegate returned without an answer." answer ]
[ "Caller received delegate tools: " swap concat ]
returned-answer-policy
```

`returned-answer-policy` is the higher-level shorthand above `returned-answer` plus `finalize-from` for prompt-return and checklist-return style caller flows.

## Parse Returned YAML Once

Use `returned-yaml` when a caller flow receives a YAML decision from a delegate through `last_delegated_result.answer` and the repeated pattern is:

- handle the missing-answer branch once
- parse the returned YAML
- continue with routing or finalization logic against the parsed mapping

```text
[ "Delegate returned without an answer." answer ]
[
  dup "route" dict-get dup "normalized.final_route" shared!? drop
  "normalized.final_route" shared@
  [
    "approve" [ "router.approve_route" handoff ]
    "default" [ "router.review_route" handoff ]
  ] switch
]
returned-yaml
```

`returned-yaml` is now the canonical caller-side shorthand for structured-return examples that used to repeat `last_delegated_result.answer`, `none?`, and `yaml>` in every router.

## Parse A Structured Delegate Return And Route

When the delegate should return a machine-readable decision, have it answer with a YAML mapping string and parse that string in the caller with `returned-yaml`.

```text
[ "Delegate returned without an answer." answer ]
[
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
returned-yaml
```

This pattern is used by `stackvm_structured_return_routing_example`.

## Route From A Nested Structured Delegate Return

When the delegate should return a nested machine-readable decision, prefer `return-field-route-flow` so the caller can declare nested returned-field specs with defaults instead of hand-writing `returned-yaml` plus `get-in?` logic.

```text
"nested_structured_return_routing_payload.yaml"
[
  common.payload-data "payload" store-set
  "payload" store-get common.normalize-item-titles
  "payload" store-get common.store-normalized-source
  common.store-normalized-summary
]
"router.confirm_delegate"
[ "Delegate returned without an answer." answer ]
[
  "decision.route" "normalized.final_route" "review"
  "decision.note" "normalized.delegate_note" "no note"
  "meta.source" "normalized.delegate_source" "unspecified"
]
[ "normalized.final_route" shared@ ]
[
  "approve" "router.approve_route"
  "escalate" "router.escalate_route"
  "default" "router.review_route"
]
return-field-route-flow
```

This pattern is used by `stackvm_nested_structured_return_routing_example`.

## Finalize From A Structured Delegate Return

When the delegate should return a machine-readable decision but the caller should still produce the final answer, prefer `return-field-finalize-flow` so the caller can declare the returned-data contract directly.

```text
"structured_finalize_payload.yaml"
[
  common.payload-data "payload" store-set
  "payload" store-get common.normalize-item-titles
  "payload" store-get common.store-normalized-source
  common.store-normalized-summary
]
"router.confirm_delegate"
[ "Delegate returned without an answer." answer ]
[
  "mode" "normalized.delegate_mode" None
  "message" "normalized.delegate_message" None
]
[
  "finalized: "
  "normalized.summary" shared@ concat
  " | mode=" concat
  "normalized.delegate_mode" shared@ concat
  " | note=" concat
  "normalized.delegate_message" shared@ concat
]
return-field-finalize-flow
```

This pattern is used by `stackvm_structured_return_finalize_example`.

## Finalize From A Nested Structured Return With Defaults

When the delegate returns nested YAML, prefer `return-field-finalize-flow` so optional nested fields and defaults stay visible as field-spec data instead of inline `get-in?` code.

```text
"nested_structured_return_payload.yaml"
[
  common.payload-data "payload" store-set
  "payload" store-get common.normalize-item-titles
  "payload" store-get common.store-normalized-source
  common.store-normalized-summary
]
"router.confirm_delegate"
[ "Delegate returned without an answer." answer ]
[
  "decision.mode" "normalized.delegate_mode" "unknown"
  "decision.note" "normalized.delegate_note" "no note"
  "meta.source" "normalized.delegate_source" "unspecified"
]
[
  "nested finalized: "
  "normalized.summary" shared@ concat
  " | mode=" concat
  "normalized.delegate_mode" shared@ concat
  " | note=" concat
  "normalized.delegate_note" shared@ concat
  " | delegate_source=" concat
  "normalized.delegate_source" shared@ concat
]
return-field-finalize-flow
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
- Start from `stackvm_nested_structured_return_routing_example` when a delegate should return nested YAML and the caller should route from nested returned fields through declarative field specs with defaults.
- Start from `stackvm_structured_return_finalize_example` when a delegate should return a structured YAML decision that the caller will parse into the final answer after multi-item normalization.
- Start from `stackvm_nested_structured_return_example` when a delegate should return nested YAML and the caller should finalize from nested returned fields through declarative field specs with defaults after multi-item normalization.
- Start from `stackvm_checklist_handoff_example` when checklist input should select one of several downstream delegates.
- Start from `stackvm_multistage_pipeline_example` when two structured interactions should happen across caller and delegate stages in one run after multi-item normalization.
- Start from `stackvm_nested_router_example` when the source data is deep and partially optional.
