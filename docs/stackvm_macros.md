# StackVM Macros

This document is the canonical reference for the current StackVM compile-time macro surface.

Use this together with `markdown_assets.md` for VM flow loading and `stackvm_cookbook.md` for higher-level authoring recipes.

## What Macros Are For

StackVM macros expand over parsed AST before runtime execution begins.

- Use `define` when you want a reusable runtime helper word, especially for repeated YAML literals, parsing helpers, and normalization steps.
- Use a built-in macro when you want a compact authoring form for a recurring control-flow shape such as tool-first loading or exact-match prompt routing.
- Use `defmacro` when neither of those is enough and you want to create a new postfix authoring surface over ordinary StackVM.

Macros are not raw text substitution and they are not YAML templating. They consume syntax arguments from the StackVM AST and produce ordinary executable StackVM AST.

## Expansion Pipeline

For VM-backed flows, the runtime currently:

1. loads raw VM source through `pocketcode/core/stackvm_loader.py`
2. parses StackVM source through `pocketcode/core/stackvm_parser.py`
3. links modules and lowers compile-time module forms through `pocketcode/core/stackvm_loader.py`
4. collects source-level authoring warnings and validates executable AST constraints through `pocketcode/core/stackvm_validator.py`
5. expands compile-time macros through `pocketcode/core/stackvm_expander.py`
6. executes the expanded AST through `pocketcode/core/agent_stack_vm.py`

Compile-only forms such as `module`, `export`, `import`, `defmacro`, `syntax-quote`, `unquote`, `unquote-splice`, and `gensym` must not survive into the executable AST.

## Definition Surface

Basic macro definition:

```text
[ value ] [ value "Result: " swap concat answer ] "emit-answer" defmacro
```

Syntax-quoted macro definition:

```text
[ value ] [ [ value unquote ] "Result: " swap concat answer ] syntax-quote "emit-answer" defmacro
```

Current rules:

- the form is postfix: parameter quotation, template quotation, optional `syntax-quote`, macro name, then `defmacro`
- parameter names must be symbols inside the parameter quotation
- macro invocations are ordinary postfix StackVM and consume the required number of immediately preceding syntax arguments
- quotations can be passed as syntax arguments
- macros may be defined inline in `vm_source` or in loaded `vm_module` or `vm_file` sources
- imported macro names behave the same way as imported helper words because module linking happens before macro expansion
- when a flow uses `vm_module_prefixes`, user-authored macro names from that module are rewritten to qualified names such as `common.read-file-once` during source assembly

## Modules

StackVM still executes against one linked program, but loaded helper files can now declare explicit modules, exports, and imports:

```text
"common" module
[ "payload" ] "payload-data" define
"payload-data" export
```

```text
"router" module
"common.payload-data" import
[ payload-data answer ] "route" define
"route" export
```

Current behavior:

- `"name" module` declares the module namespace for one loaded file or inline source block
- `"local-name" export` exposes a local `define` or `defmacro` name to other modules as `module.local-name`
- `"other.symbol" import` imports that exported symbol into the current module under its last path segment
- `"other.symbol" "alias" import` imports that exported symbol under an explicit local alias
- duplicate module names, duplicate exported symbols, unresolved imports, and import cycles fail during source assembly
- `module`, `export`, and `import` are compile-time forms only and do not survive into the executable AST

## Compatibility Prefixes

Explicit modules are now the preferred authoring model. Flows may still assign prefixes to loaded helper modules:

```yaml
vm_modules:
  - vm/common
  - vm/router
vm_module_prefixes:
  vm/common: common
```

Compatibility behavior:

- the loader rewrites unqualified user-defined `define` and `defmacro` names from the prefixed module into qualified names such as `common.payload-data`
- references to those module-local user names inside the same prefixed module are rewritten to the same qualified names
- call sites in other modules should use the qualified names directly, such as `common.payload-data`
- built-in words and host words are not prefixed
- this compatibility path effectively exports all local user-defined names from that module under the assigned prefix
- when a file already declares `"name" module`, that declared name must match any configured compatibility prefix for the same ref

## Template Modes

Legacy template mode:

- the template quotation is cloned and substituted by AST node identity
- symbol parameters in the template are replaced by the supplied syntax arguments
- this is useful for small wrappers where simple substitution is enough

Syntax-quote mode:

- `[ name unquote ]` inserts one syntax argument
- `[ name unquote-splice ]` splices a quotation/list syntax argument into the surrounding list
- `[ "prefix" gensym ]` produces a fresh symbol such as `__prefix_1`
- nested lists are expanded recursively in compile-time context

`syntax-quote` is the preferred mode for non-trivial macros because it makes insertion and splicing explicit.

## Built-In Macros

The current built-in library is loaded automatically:

- `when`: `cond body when` expands to an `if` that runs `body` only when `cond` is truthy
- `unless`: `cond body unless` expands to the negated `when` shape
- `shared-or`: `path fallback shared-or` reads `shared@` and falls back when the value is `None`
- `tool-once`: `tool_name args_expr later_turn tool-once` expands to the canonical first-turn `tool-request` plus later-turn branch
- `delegate-return`: `target_agent result_path delegate-return` expands to “handoff when missing, otherwise answer from result path”
- `finalize-from`: `value_expr finalize-from` evaluates a quotation and then answers from its result
- `prompt-route`: `request_expr cases prompt-route` expands to `prompt-interaction` followed by `switch`

Current builtin constraints:

- built-ins that need multi-step expressions, especially `tool-once` and `prompt-route`, expect those expressions as quotations and call them after expansion
- `delegate-return` does not set `pending_handoff_policy` automatically; callers still need to store that policy explicitly

## Authoring Examples

Wrap a recurring answer shape:

```text
[ value ]
[ [ value unquote ] "Macro says: " swap concat answer ]
syntax-quote "answer-with-prefix" defmacro

"hello" answer-with-prefix
```

Wrap a recurring tool-first pattern:

```text
[ args later_turn ]
[ "core.read_file" [ args unquote ] [ later_turn unquote ] tool-once ]
syntax-quote "read-file-once" defmacro

[ "{path: payload.yaml}" yaml> ]
[
  last-tool-result failure?
  [ "Could not load payload." answer ]
  [ last-tool-result "content" dict-get answer ]
  if
]
read-file-once
```

Splice a quotation body into surrounding generated code:

```text
[ body ]
[ [ body unquote-splice ] answer ]
syntax-quote "answer-from" defmacro

"hello"
[ "Result: " swap concat ]
answer-from
```

Generate a fresh helper symbol:

```text
[ ]
[ [ "tmp" gensym ] ] syntax-quote "fresh-name" defmacro
```

For a checked-in end-to-end example, see `examples/stackvm_macro_authoring_example/`.

## Debugging And Introspection

Current runtime fields for VM flows:

- `last_vm_source`: combined pre-expansion VM source
- `last_vm_expanded_source`: serialized expanded executable AST
- `last_vm_expansion_metadata`: includes `expansion_count`, `macro_names`, `builtin_macro_names`, `gensym_count`, ordered `expansion_trace`, and ordered `expansion_frames`
- `last_vm_validation_warnings`: non-fatal source-level warnings collected before macro expansion

Each `expansion_frames` entry now records the expanded macro name, whether it was built-in, expansion depth, the macro call-site location when known, the macro definition location when known, the parent macro that generated the current expansion when applicable, serialized syntax arguments, and the immediate expanded form.

Macro expansion failures retain an ordered macro trace so nested failures identify the expansion path.

## Current Limitations

Current macro support is intentionally limited:

- there is no richer compile-time evaluator beyond syntax substitution and limited compile forms
- hygiene is limited to generated symbol names from `gensym`
- macros expand before runtime host words execute; macros do not run tools, prompts, handoffs, or answers during expansion

Current diagnostics still have limits:

- expansion frames track source locations for parsed source forms and macro definitions, but nested generated forms inherit the parent call-site instead of a full source map
- there is still no complete per-node source map from expanded AST back to original source spans

## Example References

- `examples/stackvm_tool_normalize_example/`: built-in `tool-once`
- `examples/stackvm_parallel_tool_map_example/`: built-in `tool-once` around tool-first fan-out
- `examples/stackvm_reduce_tool_example/`: built-in `tool-once` around tool-first fan-in
- `examples/stackvm_threshold_router_example/`: built-in `tool-once` plus aggregate routing
- `examples/stackvm_buttons_example/`: built-in `tool-once` plus `prompt-route`
- `examples/stackvm_delegate_return_example/`: built-in `tool-once` plus `delegate-return`
- `examples/stackvm_macro_authoring_example/`: user-authored `defmacro`, `syntax-quote`, `unquote`, and `unquote-splice`
