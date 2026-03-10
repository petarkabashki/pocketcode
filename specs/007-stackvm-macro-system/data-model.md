# Data Model: StackVM Macro System

## Overview

This design introduces compile-time entities for StackVM authoring while preserving the existing runtime execution model.

## Compile-Time Entities

### MacroDefinition

Represents one named macro transformer.

Suggested fields:

- `name`: macro identifier
- `parameters`: ordered parameter list
- `rest_parameter`: optional variadic capture
- `body_ast`: syntax-producing AST
- `source_ref`: source file or inline source identifier
- `source_span`: optional location metadata

### MacroExpansionContext

Carries state during expansion.

Suggested fields:

- `macros`: mapping of macro names to `MacroDefinition`
- `expansion_depth`: current recursion depth
- `max_expansion_depth`: guardrail limit
- `gensym_counter`: monotonic integer for hygienic names
- `source_map`: original-node to expanded-node metadata

### SyntaxNode

Represents a parsed StackVM form before runtime execution.

Suggested variants:

- literal node
- symbol node
- quotation node
- macro-definition node
- syntax-quote node
- unquote node
- unquote-splice node

### ExpandedProgram

Represents the fully expanded ordinary StackVM program.

Suggested fields:

- `ast`: executable non-macro AST
- `expanded_source`: optional normalized source form for debugging
- `source_map`: macro callsite and expansion metadata
- `warnings`: optional non-fatal diagnostics

## Runtime Metadata

Macro support should not change the runtime state contract materially, but it may add debug fields to shared store for inspection.

Suggested debug fields:

- `last_vm_sources`
- `last_vm_source`
- `last_vm_expanded_source`
- `last_vm_expansion_metadata`

These are debugging aids only, not control inputs for flow logic.
