# Contract: StackVM Macro Surface

## Scope

This contract describes the proposed compile-time authoring surface for StackVM macros. It is a design target, not current runtime behavior.

## Core Forms

### Macro Definition

```text
[ arg1 arg2 ... ]
[ macro-body-producing-syntax ]
"macro-name" defmacro
```

Semantics:

- arguments are syntax arguments, not runtime-evaluated values
- the body must expand to ordinary StackVM syntax

### Syntax Quotation

```text
syntax-quote [ ... ]
```

Proposed shorthand if adopted later:

```text
`( ... )
```

Semantics:

- produces syntax rather than executing the quotation immediately

### Unquote

```text
unquote symbol
```

Proposed shorthand if adopted later:

```text
,symbol
```

Semantics:

- inserts the bound syntax argument into a syntax-quoted form

### Unquote Splice

```text
unquote-splice symbol
```

Proposed shorthand if adopted later:

```text
,@symbol
```

Semantics:

- inserts zero or more syntax nodes into an enclosing syntax-quoted list

### Hygiene

```text
gensym
```

Semantics:

- returns a generated compile-time symbol suitable for temporary bindings or helper words

### Debugging

```text
macroexpand-1
macroexpand
```

Semantics:

- expand one level or fully expand a macro-bearing form for inspection and tests

## Standard Library Candidate Macros

Recommended initial built-ins:

- `when`
- `unless`
- `shared-or`
- `tool-once`
- `prompt-route`

These should expand into existing ordinary StackVM words and host words.
