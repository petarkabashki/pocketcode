# StackVM PR 1 Spec

This document specifies the first implementation slice from `stackvm_roadmap.md`.

Scope of PR 1:

- built-in word metadata
- static stack and effect diagnostics
- richer `/stackvm inspect` output for those diagnostics

Status:

- This is an implementation spec, not a statement of current runtime behavior.
- Until the code lands, the canonical current behavior remains documented in `stackvm_cookbook.md`, `stackvm_macros.md`, `agent_system.md`, and `cli.md`.

## Problem Statement

The current StackVM validator in `pocketcode/core/stackvm_validator.py` does two things well:

- rejects compile-only forms from executable AST
- emits source-level warnings for a small set of authoring patterns

What it does not do yet:

- track stack shape through a program
- describe built-in word contracts in machine-readable form
- classify words by runtime effect kind
- statically explain why a quotation is valid or invalid for combinators such as `parallel-map` and `reduce`
- surface these semantics in `/stackvm inspect`

That gap makes StackVM harder to use as a declarative language because many mistakes are discovered only at runtime.

## PR 1 Goals

PR 1 should introduce a minimal but useful static semantics layer.

Goals:

1. define metadata for built-in words
2. validate obvious stack-shape errors before runtime
3. classify words by effect kind
4. detect effectful combinator children statically where feasible
5. expose diagnostics and metadata through `/stackvm inspect`

PR 1 should not attempt:

- a full Hindley-Milner-like type system
- precise type inference for arbitrary YAML/object shapes
- effect inference across every dynamic runtime path
- changes to the source language syntax

## Current Interfaces

Current implementation seams:

- VM execution and built-ins: `pocketcode/core/agent_stack_vm.py`
- AST validation and source warnings: `pocketcode/core/stackvm_validator.py`
- compile and inspect flow: `pocketcode/core/engine.py`
- CLI reporting: `pocketcode/cli/stackvm_commands.py`
- validator tests: `tests/unit/test_stackvm_validator.py`
- runtime tests: `tests/unit/test_agent_stack_vm.py`

PR 1 should fit those seams rather than introduce a new compiler subsystem.

## Proposed Data Model

Introduce metadata records for built-in words.

Suggested location:

- `pocketcode/core/stackvm_validator.py` for the first iteration, or
- a small new module such as `pocketcode/core/stackvm_metadata.py` if the validator file would otherwise grow too much

Recommended records:

```python
from dataclasses import dataclass, field
from typing import Literal

EffectKind = Literal[
    "pure",
    "state",
    "tool",
    "prompt",
    "handoff",
    "final",
    "llm",
    "control",
]


@dataclass(frozen=True)
class StackVmStackEffect:
    pops: int
    pushes: int | None = None
    pushes_variadic: bool = False
    notes: str = ""


@dataclass(frozen=True)
class StackVmWordMetadata:
    name: str
    stack_effect: StackVmStackEffect
    effect_kind: EffectKind
    summary: str = ""
    combinator_child_effect_mode: str | None = None
```
```

Notes:

- `pushes=None` can mean “unknown or path-dependent”
- `effect_kind` is intentionally coarse for PR 1
- `combinator_child_effect_mode` is only needed for words such as `parallel-map` and `reduce`

## Built-In Metadata Coverage

PR 1 should cover all current built-ins registered in `AgentStackVM._register_builtins()`.

Minimum examples:

- `dup`: pops 1, pushes 2, effect `pure`
- `drop`: pops 1, pushes 0, effect `pure`
- `swap`: pops 2, pushes 2, effect `pure`
- `concat`: pops 2, pushes 1, effect `pure`
- `yaml>`: pops 1, pushes 1, effect `pure`
- `store-set`: pops 2, pushes 0, effect `state`
- `store-get`: pops 1, pushes 1, effect `state`
- `shared!`: pops 2, pushes 0, effect `state`
- `shared@`: pops 1, pushes 1, effect `state`
- `call`: pops 1, pushes unknown, effect `control`
- `if`: pops 3, pushes unknown, effect `control`
- `while`: pops 2, pushes unknown, effect `control`
- `switch`: pops 2, pushes unknown, effect `control`
- `cond`: pops 1, pushes unknown, effect `control`
- `fallback`: pops 2, pushes unknown, effect `control`
- `parallel-map`: pops 2, pushes 1, effect `control`
- `reduce`: pops 3, pushes 1, effect `control`
- `define`: pops 2, pushes 0, effect `control`

Host words registered in `register_host_words()` also need metadata for inspection and effect analysis:

- `answer`: effect `final`
- `ask-user`: effect `prompt`
- `prompt-user`: effect `prompt`
- `prompt-interaction`: effect `prompt`
- `handoff`: effect `handoff`
- `tool-request`: effect `tool`
- `transition`: effect `control`
- `llm-call`: effect `llm`

## Validator Output Model

PR 1 should preserve current authoring warnings and add static diagnostics beside them.

Recommended output shape:

```python
{
    "code": "stack-underflow",
    "severity": "error",
    "message": "Word 'concat' requires 2 stack values but only 1 is guaranteed here.",
    "location": "line 3, cols 5-10",
    "span": {...},
    "word": "concat",
}
```
```

Recommended severity values:

- `error`
- `warning`
- `info`

Recommended initial diagnostic codes:

- `stack-underflow`
- `unknown-word-contract`
- `illegal-child-effect`
- `dynamic-stack-shape`

PR 1 can keep diagnostics conservative. If a branch cannot be analyzed precisely, prefer a warning over a false “safe” result.

## Static Analysis Approach

PR 1 should use abstract interpretation over executable AST.

It does not need full typing. It only needs enough state to answer:

- what is the minimum guaranteed stack depth at this point
- which effect kinds may occur in this quotation
- whether a quotation is definitely or possibly effectful

### Suggested Abstract State

```python
@dataclass
class StackVmAbstractState:
    min_depth: int
    max_depth: int | None
    effects: set[str]
    diagnostics: list[dict[str, Any]]
```
```

Interpretation rules:

- literals increase depth by 1
- built-in or host words transform depth according to metadata
- unknown user words are treated conservatively unless metadata is available
- quotations should be analyzable recursively as nested executable blocks

### Branch Semantics

For `if`:

- require three stack inputs statically
- analyze both quotations independently starting from the same pre-branch state minus consumed inputs
- merge the resulting states
- `min_depth` after merge should be the minimum of both branches
- `effects` after merge should be the union of both branches

For `switch` and `cond`:

- analyze each action quotation and merge the results conservatively

For `fallback`:

- union effects from both primary and fallback quotations

For `while`:

- PR 1 may treat post-loop depth conservatively and emit `dynamic-stack-shape` if exact shape cannot be guaranteed

### Combinator Child Analysis

For `parallel-map`:

- analyze the child quotation independently
- if the child emits any non-`pure` and non-`state` effects, emit `illegal-child-effect`
- align the rule with current runtime behavior, which rejects runtime effects in child quotations
- state mutation should also be treated as illegal in the child analysis because shared child mutations are discarded and the combinator is meant to be pure

For `reduce`:

- same child-effect rule as `parallel-map`
- reducer quotation should also preserve a coherent accumulator contract
- PR 1 only needs a basic stack contract check:
  - child quotation must be able to consume at least 2 inputs
  - child quotation must leave at least 1 output

## User-Defined Words In PR 1

PR 1 does not need a new source syntax for explicit user-word signatures.

Recommended first-pass behavior:

- record user-defined words discovered from `define`
- analyze the quotation body when possible
- cache inferred metadata for that user word in the same analysis pass

Conservative fallback:

- if a user word cannot be inferred safely, mark it as `unknown-word-contract`
- do not fail execution for that alone
- surface it in inspect output and diagnostics

This keeps PR 1 incremental and avoids designing a signature syntax too early.

## Validator API Changes

Current public functions:

- `validate_stackvm_ast(ast: list[Any]) -> None`
- `collect_stackvm_authoring_warnings(...) -> list[dict[str, Any]]`

Recommended additions:

```python
def analyze_stackvm_ast(
    ast: list[Any],
    *,
    source: str | None = None,
    include_host_words: bool = True,
) -> dict[str, Any]:
    ...
```
```

Suggested returned fields:

- `diagnostics`
- `max_stack_depth`
- `final_min_stack_depth`
- `effects`
- `word_metadata_summary`
- `user_word_summaries`

Recommended compatibility behavior:

- keep `validate_stackvm_ast()` as the executable-AST guard for compile-only forms
- call `analyze_stackvm_ast()` from the engine compile path to collect richer diagnostics

## Engine Integration

Current compile flow in `pocketcode/core/engine.py` already collects:

- parsed source
- token count
- authoring warnings
- expanded AST
- serialized expanded source

PR 1 should extend that compile result with:

- `analysis`
- `diagnostic_count`
- `diagnostics`
- `effect_kinds`
- `max_stack_depth`
- `final_min_stack_depth`

Recommended integration point:

- after expansion and executable-AST validation
- before the final inspect/run metadata payload is returned

Rationale:

- analysis should run on the executable AST, not the raw compile-time AST
- the compile pipeline should continue to reject invalid executable forms first

## CLI Changes

Current `/stackvm inspect` output already prints warnings and expanded source.

PR 1 should extend it to print:

- diagnostic count
- effect kinds
- max stack depth
- final guaranteed stack depth

Illustrative output:

```text
StackVM flow: example.route
  Tokens        : 82
  Warnings      : 1
  Diagnostics   : 2
  Effects       : prompt, state
  Max stack     : 4
  Final min     : 0
    - error stack-underflow (line 9, cols 3-8): Word 'concat' requires 2 stack values but only 1 is guaranteed here.
    - warning illegal-child-effect (line 14, cols 5-24): parallel-map child quotation may emit prompt effects.
```
```

The CLI should keep the current warnings block and add a diagnostics block below it.

## Test Plan

### Validator Tests

Add tests in `tests/unit/test_stackvm_validator.py` for:

- stack underflow on a simple built-in sequence
- no diagnostic for a valid literal-plus-built-in sequence
- `parallel-map` child with `answer`
- `parallel-map` child with `tool-request`
- `reduce` child with invalid stack contract
- `if` branch merge preserving conservative stack depth
- user-defined word inference for a simple helper

### Runtime Tests

Existing runtime tests in `tests/unit/test_agent_stack_vm.py` should remain mostly unchanged.

Add or adjust only where needed to ensure:

- runtime behavior still matches current semantics
- static analysis does not require runtime changes to keep examples working

### CLI/Engine Tests

If inspect payload tests already exist or are easy to add, cover:

- new `diagnostics` payload fields
- stable behavior when analysis returns only warnings and no errors

## File-By-File Plan

### `pocketcode/core/stackvm_validator.py`

Changes:

- keep compile-only form validation
- add metadata tables or import them from a small helper module
- add `analyze_stackvm_ast()`
- add abstract-state helpers
- preserve current authoring warning functions

Keep file size in mind. If this file grows too much, split metadata or diagnostics formatting into a helper module.

### `pocketcode/core/agent_stack_vm.py`

Changes:

- optionally expose a canonical list of built-in and host word names for reuse
- avoid duplicating built-in contract knowledge in more than one place

Recommended constraint:

- do not entangle runtime execution with static analysis logic
- the validator should consume metadata, not call into the VM interpreter

### `pocketcode/core/engine.py`

Changes:

- call `analyze_stackvm_ast()` during StackVM compilation
- store diagnostics and analysis summary in inspect/run metadata

### `pocketcode/cli/stackvm_commands.py`

Changes:

- print diagnostic counts and details
- print effect and stack summaries

### `tests/unit/test_stackvm_validator.py`

Changes:

- add focused tests for analysis behavior

## Open Questions

These questions do not need to block PR 1, but the implementation should make a reasonable choice and document it.

1. Should `store-get` and `shared@` be classified as `state` or `pure-read`?
Recommended PR 1 answer: `state`, to keep the effect taxonomy simple.

2. Should user words with unknown contracts be errors or warnings?
Recommended PR 1 answer: warnings.

3. How precise should loop analysis be?
Recommended PR 1 answer: conservative warning-based treatment for `while`.

4. Should diagnostics ever block compilation in PR 1?
Recommended PR 1 answer: only existing executable-AST validation should hard-fail. New analysis diagnostics should initially be non-fatal and surfaced for inspection.

## Definition Of Done

PR 1 is complete when:

- built-in and host words have machine-readable metadata
- the validator can detect obvious stack underflow cases
- combinator child quotations are checked for illegal effects conservatively
- `/stackvm inspect` shows diagnostics, effect summary, and stack summary
- tests cover the new analysis behavior
- canonical docs describing current behavior are updated only where implementation has actually changed

## Recommended First Coding Sequence

1. add metadata records and a metadata table
2. add a tiny abstract interpreter for literals and simple words
3. support branch merging for `if`
4. support child quotation checks for `parallel-map` and `reduce`
5. wire analysis into engine inspect payloads
6. update CLI output
7. add tests

This order minimizes the amount of partially wired behavior and keeps the first reviewable diff coherent.
