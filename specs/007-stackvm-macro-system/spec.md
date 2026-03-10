# Feature Specification: StackVM Macro System

**Feature Branch**: `[007-stackvm-macro-system]`  
**Created**: 2026-03-10  
**Status**: Draft  
**Input**: User description: "I want really flexible macros" and follow-up design discussion about hygienic AST macros for StackVM authoring.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reuse Agent Orchestration Patterns Without Copy-Paste (Priority: P1)

As a flow author, I want to define macros for recurring agent patterns so that I can reuse orchestration logic such as guarded handoffs, prompt-driven routing, and tool-first flows without repeating low-level StackVM snippets.

**Why this priority**: Current StackVM examples are expressive enough but repetitive. Macro support is only valuable if it reduces authoring friction for the real patterns already present in the checked-in examples.

**Independent Test**: Define one or more macros in a StackVM-backed flow, expand them into ordinary StackVM, and verify that the expanded program behaves the same as the equivalent handwritten VM source.

**Acceptance Scenarios**:

1. **Given** a StackVM flow defines a macro using the macro definition surface, **When** the macro is invoked later in the same loaded program, **Then** the runtime expands it into valid ordinary StackVM before execution.
2. **Given** a macro invocation expands into the same StackVM structure as a handwritten flow, **When** both are executed, **Then** they produce equivalent runtime transitions and shared-store side effects.
3. **Given** a macro is used in a program loaded from `vm_source`, `vm_module`, or `vm_file`, **When** source loading completes, **Then** macro expansion operates over the combined parsed program rather than only inline source.

---

### User Story 2 - Compose Flexible Macros Safely (Priority: P1)

As a flow author, I want macros to accept code quotations and syntax fragments as arguments so that I can build control-flow abstractions such as `when`, `tool-once`, or `prompt-route` without relying on brittle raw text substitution.

**Why this priority**: Placeholder snippets are not sufficient for agent authoring. Useful macros need to inspect and reassemble StackVM structure while preserving valid code generation.

**Independent Test**: Define macros that use quoted code arguments, nested expansion, and list splicing, then validate that expansion produces correct AST output and rejects malformed forms precisely.

**Acceptance Scenarios**:

1. **Given** a macro accepts quotations as arguments, **When** it expands those quotations into generated code, **Then** the resulting program preserves the intended quotation boundaries and executes correctly.
2. **Given** a macro uses syntax quotation with unquote or unquote-splice, **When** it is expanded, **Then** the generated AST contains the substituted syntax nodes rather than string-concatenated text.
3. **Given** a macro invocation supplies the wrong number or shape of arguments, **When** expansion runs, **Then** the system reports a macro expansion error before runtime execution begins.

---

### User Story 3 - Debug Macro Expansion Clearly (Priority: P2)

As a flow author, I want macro expansion to be inspectable so that I can understand what a macro produced and debug authoring mistakes without guessing how the compiler rewrote my source.

**Why this priority**: A macro system that hides expansion output will be difficult to adopt and difficult to trust, especially for agent routing and prompt orchestration flows.

**Independent Test**: Expand a flow that uses macros, inspect the expansion output or metadata, and confirm that runtime and validation errors can be traced back to the original macro callsite.

**Acceptance Scenarios**:

1. **Given** a flow contains macros, **When** macro expansion completes, **Then** the expanded source or expanded AST can be surfaced for inspection in tests and debugging workflows.
2. **Given** expansion fails, **When** an error is reported, **Then** the message identifies the macro name and the relevant callsite or source location.
3. **Given** a macro expands into illegal runtime forms such as forbidden child transitions inside `parallel-map`, **When** validation runs, **Then** the error reflects the expanded program while still identifying the original macro source where practical.

### Edge Cases

- A flow may mix macro definitions, ordinary user-defined words, and plain StackVM code in the same loaded source set.
- A macro may expand into another macro invocation; recursive expansion must terminate or fail with a clear recursion-depth error.
- Macros may appear in shared helper modules loaded through `vm_module` and be used by later files or inline source within the same combined program.
- A macro may generate temporary names; the system should avoid accidental capture of user-defined words where hygiene is expected.
- Existing non-macro StackVM flows must continue to execute without behavior changes.
- Expansion errors must happen before any runtime host word executes so partially executed macro-bearing flows do not leave the shared store in an inconsistent state.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST add a compile-time macro expansion phase for StackVM-backed flows before runtime execution begins.
- **FR-002**: Macro expansion MUST operate on parsed StackVM syntax rather than raw text substitution.
- **FR-003**: The system MUST support macro definitions inside loaded StackVM program source.
- **FR-004**: The system MUST support macro invocation within the same combined StackVM program assembled from inline, module, and file-backed sources.
- **FR-005**: The system MUST support syntax quotation, unquote, and unquote-splice forms sufficient to build AST-generating macros.
- **FR-006**: Macro expansion MUST produce ordinary executable StackVM AST that the existing runtime can execute without a second runtime model.
- **FR-007**: The system MUST reject malformed macro definitions or invocations before runtime execution.
- **FR-008**: The system MUST detect runaway or cyclic macro expansion and fail with a bounded recursion-depth error.
- **FR-009**: The system MUST preserve backwards compatibility for StackVM flows that do not define or invoke macros.
- **FR-010**: The system MUST provide a way to inspect expanded output for debugging and automated tests.
- **FR-011**: The system MUST keep macro evaluation separate from runtime host-word execution; macros generate code but do not execute tools, prompts, handoffs, or answers during expansion.
- **FR-012**: The implementation SHOULD provide hygienic temporary name generation for macros that synthesize helper bindings or words.
- **FR-013**: The implementation SHOULD support a standard library of built-in macros for common agent patterns such as guarded branching and tool-first orchestration.
- **FR-014**: The implementation SHOULD validate macro-expanded programs using the same StackVM semantics as handwritten programs, including child-combinator transition rules.

### Key Entities *(include if feature involves data)*

- **Macro Definition**: A compile-time StackVM form that binds a macro name to a transformer over syntax nodes.
- **Syntax Form**: A parsed StackVM AST fragment used as macro input or output.
- **Expanded Program**: The final ordinary StackVM AST or normalized source produced after recursively expanding macro invocations.
- **Expansion Context**: Compile-time state that tracks registered macros, recursion depth, generated hygienic names, and source-location metadata.

## Assumptions

- The current StackVM parser and runtime remain the execution target; the macro system adds authoring power but does not replace the VM runtime contract.
- Hygienic AST macros provide the best flexibility-to-safety ratio for the requested authoring experience.
- The current `AgentStackVM` implementation should be split functionally rather than enlarged further when compile-time features are added.
- Macro support is introduced as a historical design increment under `specs/`; canonical current behavior remains documented in `docs/` only after implementation ships.
- Macro expansion metadata may be stored in runtime/debug fields, but expansion itself is a pre-execution concern rather than a runtime transition.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Authors can express at least five recurring checked-in StackVM orchestration patterns as reusable macros without changing runtime semantics.
- **SC-002**: 100% of existing non-macro StackVM tests continue to pass after the macro expansion phase is introduced.
- **SC-003**: Macro-bearing flows fail before runtime execution in 100% of tested malformed-definition, malformed-invocation, and recursion-depth scenarios.
- **SC-004**: Expanded output is inspectable in tests for 100% of tested macro-bearing flows.
- **SC-005**: Macro expansion plus validation overhead remains negligible relative to normal flow startup for typical StackVM programs used in this repository.
