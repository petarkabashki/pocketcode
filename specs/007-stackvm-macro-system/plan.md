# Implementation Plan: StackVM Macro System

**Branch**: `007-stackvm-macro-system` | **Date**: 2026-03-10 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/007-stackvm-macro-system/spec.md`

## Summary

Introduce a compile-time macro system for StackVM authoring using hygienic AST expansion rather than raw text substitution. The implementation keeps ordinary StackVM execution as the only runtime backend, splits parsing/expansion concerns out of the current monolithic VM module, and adds debugging and validation hooks so macro-bearing flows remain inspectable and safe.

## Technical Context

**Language/Version**: Python 3.10+ (repo currently exercised on Python 3.12)  
**Primary Dependencies**: standard library, PyYAML, pytest  
**Storage**: No new persistent storage required; optional debug metadata may be carried in memory via shared-store fields  
**Testing**: pytest unit tests around parser, expander, validator, and runtime loading; integration tests for macro-bearing flow execution  
**Target Platform**: Linux terminal environment for the existing CLI/Textual runtime  
**Project Type**: Single-project Python CLI / plugin-driven agent runtime  
**Performance Goals**: Macro expansion and validation should remain effectively instantaneous for the small-to-medium StackVM source files used in this repo  
**Constraints**: Preserve existing StackVM runtime behavior; keep code files functionally split rather than growing `agent_stack_vm.py`; do not introduce a second execution backend for macro-generated flows  
**Scale/Scope**: `pocketcode/core/agent_stack_vm.py` refactor, new StackVM parser/expander modules, runtime loader integration, tests, and post-implementation documentation updates in `docs/`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Minimalist Orchestration | ✅ PASS | The design preserves StackVM as the sole runtime execution model and adds a compile-time layer rather than a second orchestration runtime. |
| II. User-Supplied Agent Plugins | ✅ PASS | Macro support changes how StackVM source is authored and loaded, not how plugins are registered or resolved. |
| III. Shared Core Tools | ✅ PASS | Tool/prompt/handoff semantics stay in the shared runtime host words; macros only generate ordinary StackVM that uses those shared words. |
| IV. Independent Testability | ✅ PASS | Parser, expander, validator, and macro-bearing flow execution can each be tested independently. |

## Project Structure

### Documentation (this feature)

```text
specs/007-stackvm-macro-system/
├── plan.md
├── spec.md
├── data-model.md
├── tasks.md
└── contracts/
    └── macro-surface.md
```

### Source Code (repository root)

```text
pocketcode/core/
├── agent_stack_vm.py              # Execution-only VM surface after refactor
├── agent_runtime.py               # Calls parse/expand/execute pipeline for VM flows
├── stackvm_loader.py              # Source assembly and file/module resolution extracted from agent_stack_vm.py
├── stackvm_parser.py              # Tokenization and ordinary AST parsing
├── stackvm_macros.py              # Macro definition model, syntax-quote helpers, built-in macros
├── stackvm_expander.py            # Recursive macro expansion, hygiene, and expansion metadata
└── stackvm_validator.py           # Validation over expanded AST, including existing transition rules

docs/                              # Updated only after implementation ships
├── markdown_assets.md             # Macro-capable StackVM authoring surface
├── architecture.md                # Load/expand/validate/execute order
└── stackvm_cookbook.md            # Example macros and authoring guidance

tests/
├── unit/
│   ├── test_agent_stack_vm.py
│   ├── test_stackvm_parser.py
│   ├── test_stackvm_expander.py
│   └── test_stackvm_validator.py
└── integration/
    └── test_stackvm_macro_flows.py
```

**Structure Decision**: Split the current mixed concerns in `agent_stack_vm.py` into dedicated parser, loader, expander, and validator modules. Keep `AgentStackVM` focused on runtime execution and built-in/runtime host words.

## Phases

### Phase 1: Refactor Current StackVM Boundaries

Goal: separate execution from loading/parsing so compile-time features have a stable insertion point.

Planned changes:

- Move `load_stackvm_program_source()`, `_resolve_stackvm_ref()`, and `_load_stackvm_file()` out of [agent_stack_vm.py](/media/mu6mula/Data1/AI-Stuff/PocketCoder/pocketcode/core/agent_stack_vm.py) into a new loader module.
- Move tokenization and ordinary AST parsing out of [agent_stack_vm.py](/media/mu6mula/Data1/AI-Stuff/PocketCoder/pocketcode/core/agent_stack_vm.py) into a parser module.
- Keep execution helpers, built-ins, host words, and child-VM semantics in [agent_stack_vm.py](/media/mu6mula/Data1/AI-Stuff/PocketCoder/pocketcode/core/agent_stack_vm.py).
- Update [agent_runtime.py](/media/mu6mula/Data1/AI-Stuff/PocketCoder/pocketcode/core/agent_runtime.py) to load source through the new loader and execute a prebuilt AST or pre-expanded source.

Primary functions impacted:

- `AgentRuntime._run_vm_agent()`
- `AgentRuntime._run_stackvm_program()`
- `AgentStackVM.eval()`
- `AgentStackVM.execute_ast()`

### Phase 2: Add Macro-Aware AST Model And Expander

Goal: introduce compile-time syntax forms and macro expansion over structured AST.

Planned changes:

- Define syntax node helpers in a new macro/expander layer rather than overloading runtime execution state.
- Add macro definition support: `defmacro`.
- Add syntax construction forms:
  - `syntax-quote`
  - `unquote`
  - `unquote-splice`
  - shorthand surface if adopted later
- Add recursive expansion with bounded depth and source metadata tracking.
- Add hygienic name generation via `gensym`.
- Expose expansion helpers for tests and debugging:
  - `macroexpand-1`
  - `macroexpand`

Primary modules/functions to add:

- `stackvm_macros.py`
  - `MacroDefinition`
  - `MacroExpansionContext`
  - built-in macro registration
- `stackvm_expander.py`
  - `expand_program_ast()`
  - `expand_node()`
  - `syntax_quote()`
  - `gensym()`

### Phase 3: Validate Expanded Programs

Goal: ensure macro-generated flows are held to the same semantic rules as handwritten StackVM.

Planned changes:

- Add validation passes over expanded AST before execution.
- Reuse current runtime constraints, especially:
  - child quotation transition restrictions in `parallel-map`
  - child quotation transition restrictions in `reduce`
  - malformed branch pair structures for `switch` and `cond`
- Add macro-specific validation:
  - unknown macro
  - wrong arity
  - invalid unquote placement
  - invalid splice usage
  - recursion limit

Primary modules/functions to add:

- `stackvm_validator.py`
  - `validate_expanded_program()`
  - `validate_macro_invocation()`
  - `validate_expansion_depth()`

### Phase 4: Integrate Expansion Into Runtime Loading

Goal: make macro-bearing flows run through the same VM runtime path with inspectable expansion output.

Planned changes:

- Update [agent_runtime.py](/media/mu6mula/Data1/AI-Stuff/PocketCoder/pocketcode/core/agent_runtime.py) so the VM path becomes:
  1. load source
  2. parse
  3. expand macros
  4. validate expanded AST
  5. execute expanded AST
- Store expansion debug metadata in shared store for tests/debugging, for example:
  - `last_vm_source`
  - `last_vm_expanded_source`
  - `last_vm_expansion_metadata`
- Ensure non-macro flows still follow the same path but with a no-op expansion step.

Primary functions impacted:

- `AgentRuntime._run_vm_agent()`
- `AgentRuntime._run_stackvm_program()`

### Phase 5: Ship Initial Macro Standard Library

Goal: prove that macros reduce real authoring repetition in current StackVM examples.

Recommended first built-ins:

- `when`
- `unless`
- `shared-or`
- `tool-once`
- `prompt-route`

Validation target:

- rewrite at least a few checked-in examples or test-only fixtures using these macros
- compare expanded output against equivalent handwritten StackVM patterns

## File-Level Implementation Notes

### [pocketcode/core/agent_stack_vm.py](/media/mu6mula/Data1/AI-Stuff/PocketCoder/pocketcode/core/agent_stack_vm.py)

Refactor target:

- Keep only execution-oriented concerns here:
  - runtime stack
  - built-in words
  - runtime host words
  - child-VM behavior
  - AST execution
- Remove source loading and parsing concerns to keep file size under control and make compile-time phases composable.

### [pocketcode/core/agent_runtime.py](/media/mu6mula/Data1/AI-Stuff/PocketCoder/pocketcode/core/agent_runtime.py)

Integration target:

- call new loader/parser/expander/validator pipeline in `_run_vm_agent()`
- keep transition handling unchanged after expansion
- surface expansion metadata for debugging

### New `stackvm_*` Modules

Design target:

- `stackvm_loader.py`: source assembly only
- `stackvm_parser.py`: token stream -> AST
- `stackvm_macros.py`: macro definitions and built-in macro registry
- `stackvm_expander.py`: compile-time expansion engine
- `stackvm_validator.py`: post-expansion validation

This split keeps each file focused and within the repo’s practical file-size guidance.

## Testing Strategy

Unit tests:

- parser still round-trips current ordinary StackVM source
- macro definitions register correctly
- `syntax-quote`, `unquote`, and `unquote-splice` build expected AST
- recursion and malformed invocations fail before runtime
- expanded AST obeys existing runtime transition restrictions

Integration tests:

- macro-bearing flow executes identically to equivalent handwritten StackVM
- loaded macros can come from `vm_module`/`vm_file` helpers
- expansion metadata is exposed for inspection
- existing non-macro StackVM examples continue to pass unchanged

## Rollout Recommendation

1. Refactor loader/parser boundaries first with no macro behavior changes.
2. Add expander and validator behind unit tests.
3. Integrate into runtime as a no-op for non-macro programs.
4. Add a small built-in macro library and example fixtures.
5. Update canonical docs in `docs/` only after runtime support ships.
