# StackVM Explicit Type Signatures Spec

This document specifies the implementation of Explicit Type Signatures and Advanced Dict Shape Inference for StackVM.

## Problem Statement

Currently, the static analyzer (`analyze_stackvm_ast`) infers the contracts of user-defined helpers by replaying their body quotations against abstract stacks. While this works well for simple cases, it falls short when:
1.  The helper relies on deeply dynamic data, causing the analyzer to degrade to `["unknown"]` shapes.
2.  The author wants to enforce a strict boundary (e.g., "This helper must *always* consume an int and a string and leave a dict").
3.  A `schema-apply` validates a dictionary, but the analyzer's shape tracking simply records `["dict"]` without knowing *which* keys are statically guaranteed to exist, leading to missed warnings for typos in downstream `dict-get` calls.

## Goals

1.  Introduce a signature syntax `( in -- out )` to the StackVM parser.
2.  Allow attaching these signatures to `define` and `defmacro`.
3.  Enhance `pocketcode/core/stackvm_validator.py` to validate the helper body against its explicit signature and use that signature at call sites.
4.  Enhance dictionary shape tracking to remember statically known keys and their types.

## Language Syntax

We will introduce parenthesis `(` and `)` as structural tokens that create a signature block. The syntax for defining a typed helper will be:

```text
[ "score" dict-get 10 > ] ( dict -- bool ) "is-high-score" define
```

At compile-time (macro expansion), the signature block will be parsed, recorded as metadata, and then **stripped** from the executable AST. This ensures the runtime `define` word still only sees `[ body ] "name" define` and requires zero changes to the VM interpreter itself.

## Proposed Architecture

### 1. Parser Updates (`pocketcode/core/stackvm_parser.py`)
*   Update `STACKVM_TOKEN_RE` to match `\(` and `\)`.
*   Update `parse_stackvm_source_with_spans` to track `(` and `)` boundaries alongside `[` and `]`.
*   Parse the contents into a new AST node format, e.g., `("sig", [("sym", "dict"), ("sym", "--"), ("sym", "bool")])`.

### 2. Expander Updates (`pocketcode/core/stackvm_expander.py`)
*   When the expander encounters `("sig", ...)` followed by `("str", "name")` and `("sym", "define")`, it should:
    1.  Extract the signature.
    2.  Store it in a side-channel or attach it to the `define` AST node as an extended tuple (if the validator runs before stripping), OR strip it entirely and let the validator look at the pre-expanded/expansion-frame AST.
    *Implementation preference:* Expand `[ body ] ("sig", ...) "name" define` into a special `("typed-define", sig, body, name)` node for the validator, which the final executable serializer unwraps back to `[ body ] "name" define`.

### 3. Validator Updates (`pocketcode/core/stackvm_validator.py`)
*   **Signature Enforcement:** When analyzing `define` with a signature, simulate the body starting with a stack matching the `in` types. Assert that the final stack matches the `out` types exactly. If it fails, emit a new diagnostic: `signature-mismatch`.
*   **Call Site Inference:** When the helper is called, trust the explicit `out` types (e.g., `["bool"]`) instead of falling back to `["unknown"]`.
*   **Dict Key Inference:** Extend the abstract stack value representation. Instead of just `"dict"`, allow `{"kind": "dict", "keys": {"score": "int", "name": "str"}}`.
*   **Schema Integration:** Hardcode support for `schema-apply`. When `schema-apply` succeeds, inspect the schema literal on the stack. If it defines `properties`, populate the `keys` mapping of the resulting `"dict"`.
*   **Dict-Get Validation:** When `dict-get` is called on a dict with known keys, if the requested key (as a literal string) is missing, emit a new diagnostic: `unknown-dict-key`.

## Diagnostic Codes to Add

*   `signature-mismatch`: "Helper 'is-high-score' signature declares ( dict -- bool ) but body leaves [ int ]."
*   `unknown-dict-key`: "Key 'scroe' is not statically known to exist in this dictionary."

## Test Plan

**`tests/unit/test_stackvm_parser.py`**
*   Test that `( int -- str )` parses into the correct `("sig", ...)` AST structure.
*   Test that unbalanced `(` or `)` raise a `SyntaxError`.

**`tests/unit/test_stackvm_validator.py`**
*   Test that `analyze_stackvm_ast` respects the explicit output shape of a typed helper.
*   Test that a helper body leaving 2 items but declaring `( -- int )` triggers `signature-mismatch`.
*   Test that parsing a schema with `schema-apply` allows the analyzer to catch a typo in a subsequent `dict-get`.

## Definition of Done

*   The `(` and `)` tokens are successfully parsed.
*   Explicit signatures govern stack shape analysis and emit warnings when the body disobeys the contract.
*   Schema definitions correctly inform downstream `dict-get` type checking.
*   The runtime execution engine requires no changes, as signatures are erased before execution.