# StackVM PR 6 Spec (Formatter & Linter)

This document specifies the first "Day 2" implementation slice from `stackvm_roadmap.md`: the StackVM Formatter and Linter.

## Problem Statement

Because StackVM relies heavily on postfix syntax and deeply nested quotations (`[ ... ]`), arbitrary whitespace and inconsistent indentation make code hard to read and review. Additionally, certain patterns (like deeply nested `if` chains) are legal but represent code smells that could be simplified with newer macros (`cond`, `match`, etc.). 

Currently, PocketCoder lacks an auto-formatter to enforce a unified style and a linter to catch these stylistic regressions.

## PR 6 Goals

1. Introduce a configurable AST-to-source formatter.
2. Implement a `/stackvm format` CLI command to rewrite standalone `.vm` files or Markdown fenced blocks.
3. Enhance the static validation pipeline (`/stackvm check`) with code-smell linter diagnostics.

## Formatter Behavior & Rules

The formatter should reconstruct a normalized source string from the parsed AST rather than manipulating raw text.

*   **Inline vs. Multi-line Quotations:** Short quotations (e.g., `[ "Result" answer ]`) should remain inline. Quotations that exceed a character limit (e.g., 60 columns) or contain structural boundaries (like `if`, `match`, `switch`, `cond`, `parallel-map`) should break into multi-line blocks with standard 2-space indentation.
*   **String Formatting:** Preserves original string literals exactly, but normalizes single/double quotes where unambiguous.
*   **Macro Wrappers:** Formats common built-in macro invocations (e.g. `tool-once`, `prompt-route`) elegantly.
*   **YAML Blocks:** `"...yaml..." yaml>` blocks should remain formatted as readable, correctly-indented YAML if they span multiple lines.

## Linter Checks (via `/stackvm check`)

We will add non-fatal diagnostics to `pocketcode/core/stackvm_validator.py` focused on code style:

*   `nested-if-smell`: Warns when `if` structures are nested more than 2 levels deep, suggesting `cond` or `switch` instead.
*   `manual-dict-get-chain`: Warns on repetitive `dup "key" dict-get? ... shared!?` blocks, suggesting `project-fields` or `project-shared`.

## Proposed Architecture

1.  **`pocketcode/core/stackvm_formatter.py`:**
    *   Expose `format_stackvm_ast(ast: list[Any], max_width: int = 80) -> str`
    *   Expose `format_stackvm_source(source: str) -> str`
2.  **`pocketcode/cli/stackvm_commands.py`:**
    *   Add the `format` subcommand logic. If the target is a `.vm` file, write in place. If the target is a `.md` agent/flow file, specifically parse and overwrite the fenced ````vm```` or ````stackvm```` blocks.
3.  **`pocketcode/cli/command_handler.py`:**
    *   Expose `/stackvm format <flow|script|agent> <target>` to the shared command layer.

## Test Plan

Add tests in `tests/unit/test_stackvm_formatter.py`:
*   Test formatting a flat sequence of words.
*   Test deep nested quotation breaking.
*   Test formatting an existing complex flow (e.g., `stackvm_nested_router_example`) and ensure the output parses to the exact same AST (idempotent).
*   Test that `/stackvm format` modifies the `.vm` file properly without corrupting the file.

Extend tests in `tests/unit/test_stackvm_validator.py`:
*   Test that an AST containing `if [ if [ if ] ]` triggers the `nested-if-smell` diagnostic.

## Definition of Done

PR 6 is complete when the `/stackvm format` command exists, modifies code cleanly preserving execution semantics, and `/stackvm check` successfully warns on the agreed stylistic code smells.