# StackVM Roadmap

This document captures a proposed evolution path for StackVM in this repository.

Status:

- This is a forward-looking design and implementation roadmap.
- It does not change the current canonical runtime behavior described in `agent_system.md`, `markdown_assets.md`, `cli.md`, `stackvm_cookbook.md`, or `stackvm_macros.md`.
- Where this roadmap mentions future commands, validation passes, or language features, treat them as proposals until the code and canonical docs are updated.

## Goals

The current StackVM implementation is already a capable orchestration language for VM-backed flows:

- runtime words and host effects live in `pocketcode/core/agent_stack_vm.py`
- parsing lives in `pocketcode/core/stackvm_parser.py`
- compile-time macro expansion lives in `pocketcode/core/stackvm_expander.py`
- source-level warnings and executable-AST validation live in `pocketcode/core/stackvm_validator.py`
- source assembly and module linking live in `pocketcode/core/stackvm_loader.py`
- CLI inspection and execution live in `pocketcode/cli/stackvm_commands.py`

The next step is to make StackVM stronger as a stand-alone language for declarative DSLs without losing its current strengths for agent and workflow orchestration.

Primary goals:

1. make StackVM programs safer to author and easier to validate before execution
2. raise the authoring level from stack choreography to declarative data and rule expression
3. reduce coupling between the core VM and PocketCoder-specific runtime semantics
4. improve explainability, introspection, and tooling
5. establish a stable standard library and packaging model

## Non-Goals

This roadmap does not propose:

- replacing PocketCoder's current StackVM runtime in one rewrite
- removing existing host words or macro forms abruptly
- introducing a general-purpose programming language feature set unrelated to declarative DSL authoring
- breaking existing checked-in StackVM examples unless a migration path exists

## Current Constraints

The current implementation has several strengths that should be preserved:

- macros operate over AST, not text
- modules, exports, and imports already exist
- host effects are already represented with structured runtime effect metadata
- validation already emits useful authoring warnings for recurring patterns
- the `/stackvm inspect` and `/stackvm debug` flows already provide useful introspection

The main gaps for stand-alone DSL use are:

- no static stack-effect typing
- no effect declarations for words
- no first-class pattern matching or destructuring
- limited immutable data transformation vocabulary
- strong coupling between core execution and PocketCoder host words
- incomplete source maps through macro expansion
- limited standalone packaging and standard library semantics

## Phase 1: Typed Validation And Effect Analysis

Priority: highest

This phase improves safety without changing the basic language model.

### Objectives

- add stack-effect signatures to built-in words
- let user-defined words optionally declare signatures
- classify words by effect kind
- perform static validation for stack shape and effect safety
- upgrade CLI inspection output to show inferred signatures and effect usage

### Proposed Concepts

Introduce two related concepts:

1. stack signatures
2. effect categories

Illustrative signature notation:

```text
concat        ( str str -- str )
dict-get?     ( any key -- any|none )
parallel-map  ( list quotation[pure] -- list )
answer        ( any -- !final_answer )
tool-request  ( tool_name args -- !tool )
```

Illustrative effect categories:

- `pure`: no store mutation and no runtime effect
- `state`: shared-store mutation only
- `llm`: issues an LLM request
- `tool`: requests a tool
- `prompt`: requests user interaction
- `handoff`: requests agent transfer
- `final`: produces a final answer
- `control`: control-flow or structural built-ins

### Implementation Direction

Files most likely to change:

- `pocketcode/core/agent_stack_vm.py`
- `pocketcode/core/stackvm_validator.py`
- `pocketcode/core/engine.py`
- `pocketcode/cli/stackvm_commands.py`

Likely additions:

- a built-in word registry structure that records stack signature and effect metadata alongside the callable
- a validator pass that simulates stack shape through executable AST
- explicit combinator contracts for `parallel-map` and `reduce`
- inspection output fields for inferred stack/effect summaries

### Acceptance Criteria

- obvious stack underflow and arity errors are caught before runtime
- `parallel-map` and `reduce` reject effectful child quotations statically when possible
- `/stackvm inspect` reports signature and effect diagnostics
- existing examples continue to run without source changes, or warnings clearly identify migration opportunities

## Phase 2: Declarative Data And Pattern Forms

Priority: high

This phase raises the DSL level so common DSL tasks do not require repetitive `dict-get?`, `get-in?`, `none?`, and `if` chains.

### Objectives

- add first-class matching and destructuring
- add immutable collection transforms
- add more expressive declarative routing and normalization forms
- keep the surface postfix and AST-friendly

### Proposed Features

#### Pattern Matching

Illustrative forms:

```text
value
[
  [ { kind: "approve", payload: approval } ] [ approval "route.approve" handoff ]
  [ { kind: "reject", payload: rejection } ] [ rejection "route.reject" handoff ]
  [ _ ] [ "Unsupported value." answer ]
]
match
```

Possible minimum viable scope:

- literal match
- wildcard
- list destructuring
- mapping destructuring
- tagged-case routing over a named field

#### Immutable Data Operators

Recommended early additions:

- `map`
- `filter`
- `flat-map`
- `find`
- `any?`
- `all?`
- `group-by`
- `sort-by`
- `merge`

These should prefer immutable semantics so data-shaping DSLs remain predictable.

#### Schema-Aware Helpers

Illustrative capabilities:

- validate a mapping against a schema
- coerce optional primitives
- require or default nested fields declaratively
- emit precise validation failures suitable for CLI inspection and runtime reporting

### Implementation Direction

Files most likely to change:

- `pocketcode/core/agent_stack_vm.py`
- `pocketcode/core/stackvm_expander.py`
- `pocketcode/core/stackvm_validator.py`
- `tests/unit/test_agent_stack_vm.py`
- `tests/unit/test_stackvm_validator.py`
- `docs/stackvm_cookbook.md`
- `docs/stackvm_macros.md`

Implementation preference:

- add high-level authoring forms as macros first when they naturally lower into existing runtime constructs
- add runtime words only when macro expansion would be awkward, inefficient, or too opaque

### Acceptance Criteria

- checked-in examples can replace some repeated normalization branches with clearer declarative forms
- pattern failures are intelligible in `/stackvm inspect` and `/stackvm debug`
- the new forms reduce authoring noise in at least two example families

## Phase 3: Portable Host Effect ABI

Priority: high

Today the StackVM runtime is powerful largely because of PocketCoder-specific host words such as `tool-request`, `prompt-interaction`, `handoff`, `answer`, and `llm-call`.

That is useful for the current product, but it limits StackVM as a stand-alone language.

### Objectives

- define a host-independent core execution contract
- move PocketCoder-specific behavior into an adapter layer
- preserve current runtime behavior by implementing the adapter first

### Proposed Model

Separate:

1. a core VM that emits structured effects
2. host adapters that interpret those effects

Illustrative effect record kinds:

- `final_answer`
- `ask_user`
- `prompt_interaction`
- `call_tool`
- `handoff`
- `llm_call`
- `state_transition`

The core VM should know how to emit them, but not how PocketCoder routes them afterward.

### Implementation Direction

Files most likely to change:

- `pocketcode/core/agent_stack_vm.py`
- `pocketcode/core/runtime_effects.py`
- `pocketcode/core/engine.py`

Possible refactor steps:

1. formalize a small VM host interface
2. convert current host word registration to use that interface
3. keep the engine as the first host adapter
4. add a minimal standalone CLI adapter for scripts that do not require the full engine

### Acceptance Criteria

- core VM execution can run against more than one host adapter
- current PocketCoder flows keep their runtime behavior
- standalone StackVM script execution requires less synthetic engine scaffolding than today

## Phase 4: Explainability And Developer Tooling

Priority: medium

This phase is about making the language operable at scale.

### Objectives

- improve macro source maps
- improve trace readability
- add static check commands
- add explanation commands for routing and expansion
- add formatter and linter support

### Proposed CLI Additions

These are proposed commands, not current CLI behavior:

- `/stackvm check <flow|script|agent> <target> [--entry <word>]`
- `/stackvm explain <flow|script|agent> <target> [--entry <word>]`
- `/stackvm format <script_or_file>`

Suggested command semantics:

- `check`: parse, link, expand, validate, and report diagnostics without execution
- `explain`: show expansion trace, inferred effects, and branch reasoning in a human-readable form
- `format`: normalize source layout and spacing

### Implementation Direction

Files most likely to change:

- `pocketcode/cli/stackvm_commands.py`
- `pocketcode/core/stackvm_expander.py`
- `pocketcode/core/stackvm_validator.py`
- `stackvm-syntax/`
- `docs/cli.md`

### Acceptance Criteria

- expansion traces point back to authored macro call sites more reliably than today
- static checks are available without executing a flow
- debug output is readable for larger programs and nested expansions

## Phase 5: Standard Library And Packaging

Priority: medium

If StackVM is going to be authored as a language rather than only an embedded feature, it needs a stable library and package model.

### Objectives

- define a standard library layout
- formalize module versioning expectations
- make imports reproducible
- publish canonical reusable modules rather than only snippets

### Proposed Standard Library Areas

- `std.core`: structural words, control flow, stack utilities
- `std.data`: collection transforms, normalization helpers, path utilities
- `std.rules`: match, routing, rule-table helpers
- `std.effects`: host-effect wrappers and portable effect helpers
- `std.schema`: schema and coercion helpers

### Packaging Questions

Open design questions:

- should StackVM packages be file-based only, or carry package metadata
- should version resolution be exact or compatible-range based
- should package loading remain workspace-local initially
- how should trusted versus untrusted modules be separated

### Acceptance Criteria

- shared helper modules can be referenced predictably across examples and workspaces
- canonical imports no longer depend on ad hoc file conventions alone
- the standard library becomes the default place for common cookbook patterns

## Recommended Delivery Order

The practical implementation order for this repository is:

1. Phase 1: typed validation and effect analysis
2. targeted CLI inspection improvements from Phase 4
3. Phase 2: declarative data and pattern forms
4. Phase 3: portable host effect ABI
5. remaining Phase 4 tooling
6. Phase 5: standard library and packaging

Rationale:

- Phase 1 reduces runtime surprises immediately and strengthens every later feature
- earlier CLI improvements make later language work easier to debug and review
- Phase 2 increases language leverage once validation is strong enough
- Phase 3 is easier once the runtime surface is better described and validated
- packaging should come after the language surface is more stable

## Suggested PR Breakdown

### PR 1: Metadata And Static Validation Foundation

Scope:

- introduce built-in word metadata
- add validator support for stack/effect diagnostics
- surface diagnostics in `/stackvm inspect`
- document the current and new validation behavior

Implementation spec:

- `stackvm_pr1_spec.md`

### PR 2: Explainability Upgrade

Scope:

- improve macro expansion frame reporting
- add a static `/stackvm check` command
- improve debug output with stack diffs and effect summaries

### PR 3: Declarative Data Core

Scope:

- add immutable collection primitives
- add one or two high-value declarative macros
- migrate at least one checked-in example family to the cleaner forms

### PR 4: Pattern Matching

Scope:

- add `match` or an equivalent pattern facility
- add validator support and CLI explanation output for match failures
- document matching semantics in the cookbook and macro docs

### PR 5: Host ABI Extraction

Scope:

- introduce a host adapter interface
- make the current engine the default adapter
- simplify standalone script execution

## Migration Strategy

Migration should be incremental.

Guidelines:

- keep existing words working while better declarative forms are introduced
- use validator warnings before hard errors where possible
- migrate checked-in examples first so the docs remain grounded in real source
- update `docs/stackvm_cookbook.md`, `docs/stackvm_macros.md`, and `docs/cli.md` in the same PRs that change the implementation

## Success Criteria

StackVM will be materially more powerful as a stand-alone declarative DSL language when all of the following are true:

- authors can learn most common patterns from a compact standard library instead of low-level stack choreography
- authors get static feedback about stack shape, effect safety, and common routing mistakes
- host effects are portable enough that StackVM is not tightly bound to one runtime
- tooling can explain what a program expanded to, why a branch matched, and which effects a quotation may emit
- reusable modules have a clear packaging and import model

## Immediate Next Step

The recommended next implementation step is PR 1:

- define built-in word metadata
- add a first validator pass for stack and effect analysis
- expose the results through `/stackvm inspect`

That work has the best cost-to-impact ratio and creates the foundation for the rest of the roadmap.
