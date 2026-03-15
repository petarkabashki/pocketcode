---
name: authoring_stackvm
description: Best practices for authoring StackVM flows
---

# Authoring StackVM Flows

When authoring StackVM flows, always follow these rules and patterns.

## General Best Practices
1. **Explicit Signatures**: Always use explicit signatures with `define`. For example: `( in -- out )`.
   ```text
   [ dup 0 > [ 1 - fact * ] [ drop 1 ] if ]
   ( int -- int )
   "fact"
   define
   ```
2. **Exhaustiveness**: When using `switch` and `match` on enums, ensure you cover all possible cases. Provide a `"default"` branch for `switch` or `_` for `match` if not all values are explicitly handled.
3. **Single-Branch Guarding**: Use `when` instead of `if` for truthy-only logic. Use `unless` when the negative case is the only branch.
4. **Tool Use**: Do not manually loop over tool results (e.g., `last-tool-result none? ... tool-request ... if`). Use `tool-once` or `stdlib.io` macros.

## Standard Library Modules (`vm/stdlib/`)
The checked-in reusable standard-library modules live under `vm/stdlib/` and are loaded via `vm_modules`, e.g., `vm_modules: [stdlib.io, stdlib.normalize]` in the manifest.
1. **`stdlib.io`**:
   - `read-file-once`: Macro specialized for `core.read_file` via `tool-once`.
   - `read-yaml-file-once`: Reads a file and parses it with `yaml>`. Canonical pattern for single-file tool loads.
2. **`stdlib.normalize`**:
   - Helpers to reshape tool data. Includes `tool-content-yaml`, `item-title`, `normalize-item-titles`, `store-normalized-source`, `format-selected-actions`. Normalizes lists of items into `shared` state before routing/prompting.
3. **`stdlib.config`**:
   - `tool-content-schema-apply`: Parses JSON/YAML config, runs `schema-apply` using a defined `schema` on the stack. Useful for config-driven routing.
4. **`stdlib.prompt`**:
   - Reusable buttons/radio/checklist prompts (e.g., `buttons-approve-reject`, `radio-concise-blocked`). Typically customized by setting `prompt` on the dictionary before `prompt-interaction`.
5. **`stdlib.workflows`**:
   - Family macros like `define-approve-reject-answer-family` to bind shared contracts on both caller and delegate sides.

## Shaping Data
1. **Iterators**: Use `map`, `flat-map`, `filter`, `find`, `any?`, `all?`, `sort-by`, and `group-by` to shape in-memory lists without parallelism.
2. **Parallel**: Use `parallel-map` for pure data fan-out. The body quotation must avoid runtime effect side-effects (no `handoff`, `ask-user`, etc. in the child).
3. **Reducing**: Use `reduce` to accumulate list values to a single result without parallelism.

## Routing, Matching, and Control Flow Patterns
- **Exact & Structured Routing**:
  - **`switch`**: Route on exact match values.
  - **`match`**: Route on structured values directly, extract patterns using strings like `"$approval_id"`.
- **Config-Driven Routing (`schema-route`)**:
  - Normalize YAML data using `schema-apply`, save `config_errors`, and route on valid shapes with fallback. Use built-in `schema-route` over nested `dict-get?`.
- **Aggregate Then Route**:
  - Load data, map/reduce into aggregates, then route delegates via `handoff-rules` based on thresholds.
- **Normalize Then Interact / Delegate**:
  - Load data with `stdlib.io.read-yaml-file-once`.
  - Normalize with `stdlib.normalize` into `shared` memory.
  - Ask a question (`ask-from`), confirm (`prompt-store-text`), or return a structured decision to caller via defined shared workflow contracts (like `define-choice-continue-spec`, `define-choice-answer-family`).
- **Delegate Answers (`stdlib.returns`)**:
  - Use `delegate-answer` and `delegate-answer-yaml?` to safely extract exactly what the delegate handed back in `last_delegated_result.answer`.

## Module Linking (Common vs Stdlib)
Separate reusable multi-namespace functionality into `vm/stdlib/`. Use explicit module boundaries with `module`, `import`, and `export` instead of legacy common prefixes:
```text
"common" module
"stdlib.config.tool-content-schema-apply" import
"my-helper" export
```
