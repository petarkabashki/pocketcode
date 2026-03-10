# Tasks: StackVM Macro System

## Phase 1: Refactor Current VM Boundaries

- [ ] Extract StackVM source loading from `pocketcode/core/agent_stack_vm.py` into `pocketcode/core/stackvm_loader.py`
- [ ] Extract tokenization and parsing into `pocketcode/core/stackvm_parser.py`
- [ ] Keep `AgentStackVM` focused on execution and built-in/runtime word semantics
- [ ] Add refactor-only tests proving non-macro StackVM behavior remains unchanged

## Phase 2: Add Macro Expansion Engine

- [ ] Introduce macro definition and expansion context models in `pocketcode/core/stackvm_macros.py`
- [ ] Implement AST expansion in `pocketcode/core/stackvm_expander.py`
- [ ] Support `defmacro`
- [ ] Support `syntax-quote`
- [ ] Support `unquote`
- [ ] Support `unquote-splice`
- [ ] Support hygienic `gensym`
- [ ] Add bounded recursion-depth protection

## Phase 3: Validate Expanded Programs

- [ ] Add `pocketcode/core/stackvm_validator.py`
- [ ] Reject malformed macro invocations before runtime
- [ ] Reject invalid unquote/unquote-splice placement
- [ ] Validate expanded AST against existing StackVM runtime constraints
- [ ] Preserve source-location metadata for diagnostics where practical

## Phase 4: Integrate Into Agent Runtime

- [ ] Update `AgentRuntime` VM loading path to parse, expand, validate, and then execute
- [ ] Surface expanded source or equivalent debug metadata in shared store
- [ ] Add integration tests for macro-bearing VM flows
- [ ] Confirm existing non-macro StackVM examples still pass unchanged

## Phase 5: Ship Initial Macro Standard Library

- [ ] Add built-in macros for `when`, `unless`, `shared-or`, `tool-once`, and `prompt-route`
- [ ] Add focused example fixtures or test-only flows demonstrating those macros
- [ ] Update canonical `docs/` after implementation ships
