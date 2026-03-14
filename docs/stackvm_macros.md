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
- `shared-handoff`: `value path target_agent shared-handoff` writes one shared value and immediately hands off
- `tool-once`: `tool_name args_expr later_turn tool-once` expands to the canonical first-turn `tool-request` plus later-turn branch
- `delegate-return`: `target_agent result_path delegate-return` expands to “handoff when missing, otherwise answer from result path”
- `return-handoff`: `target_agent return-handoff` sets the standard `return_to_caller` policy and then hands off
- `return-delegate`: `target_agent result_path return-delegate` combines standard `return_to_caller` setup with delegate-return pass-through
- `return-flow`: `payload_file load_body delegate_target resume_body return-flow` packages the caller-side first-turn load plus return-to-caller handoff and the resumed caller-side policy after the delegate returns
- `return-answer-flow`: `payload_file load_body delegate_target missing_case value_expr return-answer-flow` packages `return-flow` together with plain returned-answer finalization
- `return-policy-flow`: `payload_file load_body delegate_target missing_case projections mode value_expr rules return-policy-flow` packages `return-flow` together with structured returned-answer routing or finalization
- `return-contract-flow`: `output_mode payload_file load_body delegate_target missing_case field_specs value_expr rules return-contract-flow` chooses the top-level caller-side return contract in one place and expands to `return-answer-flow`, `return-field-route-flow`, or `return-field-finalize-flow`
- `normalize-loaded-payload`: `normalize-loaded-payload` packages the checked-in payload normalization contract by loading `common.payload-data`, normalizing item titles, and storing the normalized source plus shared summary
- `workflow-spec`: `spec role policy workflow-spec` is the lower-level inline workflow-spec surface; it expands to the appropriate workflow contract adapter from one shared spec vocabulary
- `define-workflow-spec`: `name spec define-workflow-spec` registers one compile-time named workflow spec during expansion and emits no runtime code
- `extend-workflow-spec`: `base_name name overrides extend-workflow-spec` clones one previously declared workflow spec, merges override key/value pairs, and registers the derived named spec
- `use-workflow-spec`: `name role policy use-workflow-spec` resolves one previously declared workflow spec by name and routes it through `workflow-spec`
- `define-workflow-family`: `name family define-workflow-family` registers one compile-time workflow family with multiple role-and-policy sections such as `caller.answer` or `delegate.route`
- `extend-workflow-family`: `base_name name overrides extend-workflow-family` clones one previously declared workflow family, merges section overrides, and registers the derived family
- `use-workflow-family`: `name role policy use-workflow-family` resolves one previously declared workflow family, merges its optional `shared` section with the selected `role.policy` section, and routes the resulting spec through `workflow-spec`
- `define-choice-continue-spec`: `name payload_file kind prompt_prefix value_path options attrs match_mode prepare_expr rules define-choice-continue-spec` registers one named workflow spec for normalized direct continuation from a declarative choice table
- `define-choice-answer-spec`: `name kind prompt_prefix value_path options attrs match_mode prepare_expr delegate_rules define-choice-answer-spec` registers one named delegate-side answer workflow spec from a declarative choice table
- `define-choice-answer-family`: `name payload_file delegate_target missing_case caller_value_expr kind prompt_prefix value_path options attrs match_mode prepare_expr delegate_rules define-choice-answer-family` registers one paired caller/delegate answer workflow family from one declarative choice contract
- `define-choice-continue-answer-family`: `name payload_file kind prompt_prefix value_path options attrs match_mode prepare_expr continue_rules delegate_kind delegate_prompt_prefix delegate_value_path delegate_options delegate_attrs delegate_match_mode delegate_prepare_expr delegate_rules define-choice-continue-answer-family` registers one mixed router/delegate family for two-stage workflows that continue first and only delegate on selected branches
- `define-choice-route-family`: `name payload_file delegate_target missing_case caller_field_specs caller_value_expr caller_rules kind prompt_prefix value_path options attrs match_mode prepare_expr delegate_base_expr delegate_rules define-choice-route-family` registers one paired caller/delegate structured route family from one declarative choice contract
- `define-choice-finalize-family`: `name payload_file delegate_target missing_case caller_field_specs caller_value_expr kind prompt_prefix value_path options attrs match_mode prepare_expr delegate_base_expr delegate_rules define-choice-finalize-family` registers one paired caller/delegate structured finalize family from one declarative choice contract
- `continue-workflow-contract`: `contract continue-workflow-contract` is now the lower-level contract-entry surface for normalization-aware direct continuation workflows; it expands to `router-continue-workflow`
- `answer-workflow-contract`: `contract answer-workflow-contract` is now the lower-level contract-entry surface for plain returned-answer workflows; it dispatches to either `caller-answer-workflow` or `delegate-answer-workflow` from the same contract vocabulary
- `route-workflow-contract`: `contract route-workflow-contract` is now the lower-level contract-entry surface for structured returned-route workflows; it dispatches to either `caller-route-workflow` or the structured delegate path from the same contract vocabulary
- `finalize-workflow-contract`: `contract finalize-workflow-contract` is now the lower-level contract-entry surface for structured returned-finalize workflows; it dispatches to either `caller-finalize-workflow` or the structured delegate path from the same contract vocabulary
- `normalized-return-flow`: `output_mode payload_file delegate_target missing_case field_specs value_expr rules normalized-return-flow` is the preferred normalization-aware caller return surface; it expands to `return-contract-flow` with the standard file-load and normalization body already wired in
- `caller-answer-workflow`: `payload_file delegate_target missing_case value_expr caller-answer-workflow` is the lower-level caller-side role-specialized surface for normalization-aware plain returned-answer workflows; it expands to `normalized-answer-workflow`
- `caller-route-workflow`: `payload_file delegate_target missing_case field_specs value_expr rules caller-route-workflow` is the lower-level caller-side role-specialized surface for normalization-aware resumed route workflows; it expands to `normalized-route-workflow`
- `caller-finalize-workflow`: `payload_file delegate_target missing_case field_specs value_expr caller-finalize-workflow` is the lower-level caller-side role-specialized surface for normalization-aware resumed finalization workflows; it expands to `normalized-finalize-workflow`
- `normalized-answer-workflow`: `payload_file delegate_target missing_case value_expr normalized-answer-workflow` is the lower-level normalization-aware caller surface for plain returned-answer workflows; it expands to `normalized-return-flow` in `answer` mode
- `normalized-route-workflow`: `payload_file delegate_target missing_case field_specs value_expr rules normalized-route-workflow` is the lower-level normalization-aware caller surface for resumed route workflows; it expands to `normalized-return-flow` in `route` mode
- `normalized-finalize-workflow`: `payload_file delegate_target missing_case field_specs value_expr normalized-finalize-workflow` is the lower-level normalization-aware caller surface for resumed finalization workflows; it expands to `normalized-return-flow` in `finalize` mode
- `project-fields`: `field_specs body project-fields` packages declarative returned-field extraction specs over one parsed mapping and continues inline with `body`
- `returned-field-policy`: `missing_case field_specs mode value_expr rules returned-field-policy` packages structured returned-answer routing or finalization from declarative field specs instead of projection quotations
- `return-field-policy-flow`: `payload_file load_body delegate_target missing_case field_specs mode value_expr rules return-field-policy-flow` packages `return-flow` together with field-spec-based structured returned-answer routing or finalization
- `return-field-route-flow`: `payload_file load_body delegate_target missing_case field_specs value_expr rules return-field-route-flow` specializes `return-field-policy-flow` for downstream handoff routing
- `return-field-finalize-flow`: `payload_file load_body delegate_target missing_case field_specs value_expr return-field-finalize-flow` specializes `return-field-policy-flow` for caller-side finalization
- `maybe-handoff`: `value_expr missing_case maybe-handoff` evaluates one candidate agent, runs `missing_case` when it is `None`, otherwise hands off directly
- `indexed-value`: `list_expr index_expr missing_case body indexed-value` selects one list item, runs `missing_case` when the item is absent, otherwise continues with that selected value
- `indexed-handoff-route`: `list_expr index_expr missing_reason fallback_agent body indexed-handoff-route` selects one list item by index, records `route_reason` plus hands off to `fallback_agent` when missing, otherwise continues with that selected value
- `finalize-from`: `value_expr finalize-from` evaluates a quotation and then answers from its result
- `prompt-route`: `request_expr cases prompt-route` expands to `prompt-interaction` followed by `switch`
- `prompt-store`: `request_expr value_path body prompt-store` expands to `prompt-interaction`, stores the selected value, and then runs `body`
- `choice-request`: `kind prompt_expr options attrs choice-request` builds a structured interaction request from a choice kind, dynamic prompt quotation, declarative option table, and extra request attrs
- `summary-choice-flow`: `output_mode kind prompt_prefix value_path options attrs match_mode prepare_expr base_expr rules summary-choice-flow` is the preferred normalized-summary choice surface; it derives the prompt from `prompt_prefix` plus `normalized.summary` and then expands to `choice-flow`
- `delegate-answer-workflow`: `kind prompt_prefix value_path options attrs match_mode prepare_expr rules delegate-answer-workflow` is the lower-level delegate-side role-specialized surface for normalized-summary plain-answer workflows; it expands to `summary-answer-workflow`
- `delegate-structured-workflow`: `kind prompt_prefix value_path options attrs match_mode prepare_expr base_expr rules delegate-structured-workflow` is the lower-level delegate-side role-specialized surface for normalized-summary structured workflows; it expands to `summary-structured-workflow`
- `summary-answer-workflow`: `kind prompt_prefix value_path options attrs match_mode prepare_expr rules summary-answer-workflow` is the lower-level normalized-summary delegate surface for plain returned answers; it expands to `summary-choice-flow` in `answer` mode
- `summary-structured-workflow`: `kind prompt_prefix value_path options attrs match_mode prepare_expr base_expr rules summary-structured-workflow` is the lower-level normalized-summary delegate surface for structured YAML decisions; it expands to `summary-choice-flow` in `structured` mode
- `normalized-choice-router`: `payload_file output_mode kind prompt_prefix value_path options attrs match_mode prepare_expr base_expr rules normalized-choice-router` is the lower-level normalization-aware direct interaction surface; it expands to file load, `normalize-loaded-payload`, and then `summary-choice-flow`
- `router-continue-workflow`: `payload_file kind prompt_prefix value_path options attrs match_mode prepare_expr rules router-continue-workflow` is the lower-level router-side role-specialized surface for normalization-aware direct continuation workflows; it expands to `normalized-continue-workflow`
- `normalized-continue-workflow`: `payload_file kind prompt_prefix value_path options attrs match_mode prepare_expr rules normalized-continue-workflow` is the lower-level normalization-aware direct continuation surface; it expands to `normalized-choice-router` in `continue` mode
- `choice-flow`: `output_mode kind prompt_expr value_path options attrs match_mode prepare_expr base_expr rules choice-flow` is the lower-level top-level choice-table surface under `summary-choice-flow` and `normalized-choice-router`; it expands to `choice-policy` for direct router continuation modes and to `choice-contract` for delegate answer or structured-output modes
- `choice-policy`: `kind prompt_expr value_path options attrs match_mode prepare_expr rules choice-policy` packages `choice-request` together with `prompt-store-policy` so direct interaction flows can declare request shape and persisted route policy from one surface
- `prompt-store-policy`: `request_expr value_path match_mode prepare_expr rules prompt-store-policy` expands to `prompt-interaction`, stores the selected value, optionally runs one preparation quotation, and then routes through either exact-match switching or prioritized membership checks
- `prompt-return-policy`: `request_expr value_path match_mode prepare_expr rules prompt-return-policy` expands to `prompt-interaction`, stores the selected value, optionally runs one preparation quotation, and then answers from a rule table instead of continuing into more VM control flow
- `prompt-return-yaml-policy`: `request_expr value_path match_mode prepare_expr rules prompt-return-yaml-policy` expands to `prompt-interaction`, stores the selected value, optionally runs one preparation quotation, and then serializes a returned mapping/list value through `yaml<` before answering
- `prompt-return-merge-policy`: `request_expr value_path match_mode prepare_expr base_expr rules prompt-return-merge-policy` expands to `prompt-interaction`, stores the selected value, optionally runs one preparation quotation, merges a shared base mapping with a decision-specific mapping, serializes the result through `yaml<`, and then answers
- `prompt-decision`: `output_mode request_expr value_path match_mode prepare_expr base_expr rules prompt-decision` chooses the delegate-side output contract in one place and expands to `prompt-return-policy`, `prompt-return-yaml-policy`, or `prompt-return-merge-policy`
- `choice-decision`: `output_mode kind prompt_expr value_path options attrs match_mode prepare_expr base_expr rules choice-decision` packages `choice-request` together with `prompt-decision` so delegate flows can declare both the interaction request and the returned-output contract from one policy table
- `choice-contract`: `output_mode kind prompt_expr value_path options attrs match_mode prepare_expr base_expr rules choice-contract` chooses the top-level delegate-side contract in one place and expands to either `choice-decision` or `choice-structured-decision`
- `record-fields`: `base_expr field_specs record-fields` builds one mapping from a base mapping quotation plus declarative `path value` field specs
- `choice-structured-decision`: `kind prompt_expr value_path options attrs match_mode prepare_expr base_expr rules choice-structured-decision` packages `choice-request` together with declarative returned-field specs so structured delegates can emit YAML without handwritten `dict-set` or `set-in` branch bodies
- `prompt-store-switch`: `request_expr value_path cases prompt-store-switch` expands to `prompt-interaction`, stores the selected value, and then routes through a `switch` table
- `prompt-store-contains-switch`: `request_expr value_path prepare_expr rules prompt-store-contains-switch` expands to `prompt-interaction`, stores the selected list, runs one preparation quotation, and then routes through prioritized membership checks
- `ask-from`: `question_expr ask-from` evaluates a quotation and passes the resulting string to `ask-user`
- `prompt-store-text`: `question_expr value_path body prompt-store-text` expands to `prompt-user`, stores the reply text, and then runs `body`
- `validated-match`: `result_expr cases invalid_case validated-match` expands to the common `{success, value, errors}` envelope pattern used after `schema-check` and `schema-apply`
- `schema-route`: `errors_path value_store_path cases invalid_case schema-route` stores schema errors, optionally stores the validated value, and then routes through `validated-match`
- `handoff-rules`: `rules band_path handoff-rules` expands rule triplets into a `cond` table whose actions store a route band and hand off
- `handoff-switch`: `value_expr cases handoff-switch` evaluates one route expression and dispatches through a `switch` table whose actions all hand off
- `project-shared`: `projections body project-shared` evaluates projection quotations against one source value, stores each projected result through `shared!?`, and then continues inline with `body`
- `returned-handoff-switch`: `missing_case projections value_expr cases returned-handoff-switch` parses a returned YAML decision, projects shared fields, and routes through `handoff-switch`
- `returned-finalize`: `missing_case projections value_expr returned-finalize` parses a returned YAML decision, projects shared fields, and finalizes from one composed value expression
- `returned-policy`: `missing_case projections mode value_expr rules returned-policy` unifies the caller-side structured-return surface for either downstream handoff routing or caller-side finalization
- `returned-answer`: `missing_case body returned-answer` reads `last_delegated_result.answer`, handles the missing-answer branch, and then runs `body` against the returned value
- `returned-answer-policy`: `missing_case value_expr returned-answer-policy` reads `last_delegated_result.answer`, handles the missing-answer branch, and finalizes from one composed value expression
- `returned-yaml`: `missing_case body returned-yaml` reads `last_delegated_result.answer`, handles the missing-answer branch, parses YAML, and then runs `body`

Current builtin constraints:

- built-ins that need multi-step expressions, especially `tool-once` and `prompt-route`, expect those expressions as quotations and call them after expansion
- `shared-handoff` accepts ordinary syntax arguments and expands to one `shared!` followed by `handoff`; use it when the branch only needs to persist a reason/status before delegating
- `validated-match` expects `result_expr` and `invalid_case` as quotations; `result_expr` runs against the full schema-result envelope before matching and `cases` runs against the normalized `value`
- `schema-route` expects the schema-result envelope to already be on the stack; `errors_path` is written with `shared!`, `value_store_path` may be `None` for no stored copy, and `cases` still match against the normalized `value`
- `handoff-rules` expects one quotation containing repeating `condition band agent` triplets; each condition must be a quotation and each generated branch writes the selected band to `band_path` before `handoff`
- `handoff-switch` expects `value_expr` as a quotation and `cases` as one quotation containing repeating `match_value agent` pairs; generated branches become `switch` actions that only `handoff`
- `return-flow` expects `load_body` and `resume_body` as quotations plus plain `payload_file` and `delegate_target` syntax values; the current built-in includes the checked-in generic tool-load failure answer `"Could not load the payload."`
- `return-answer-flow` expects `load_body`, `missing_case`, and `value_expr` as quotations plus plain `payload_file` and `delegate_target` syntax values; it specializes `return-flow` plus `returned-answer-policy`
- `return-policy-flow` expects `load_body`, `missing_case`, `projections`, `value_expr`, and `rules` as quotations plus plain `payload_file`, `delegate_target`, and `mode` syntax values; it specializes `return-flow` plus `returned-policy`
- `return-contract-flow` expects `load_body`, `missing_case`, `field_specs`, `value_expr`, and `rules` as quotations plus plain `output_mode`, `payload_file`, and `delegate_target` syntax values; use `answer` for plain returned-answer callers, `route` or `handoff` for structured resumed routing, and `finalize` for structured resumed finalization
- `normalize-loaded-payload` expects the checked-in example-local `common.*` normalization facade to exist; it currently standardizes on `common.payload-data`, `common.normalize-item-titles`, `common.store-normalized-source`, and `common.store-normalized-summary`
- `workflow-spec` expects one quotation of repeating key/value pairs plus plain `role` and `policy` syntax values. `role` must be `router`, `caller`, or `delegate`. `policy` must be `continue`, `answer`, `route`, or `finalize`, with `router` limited to `continue`. Shared spec keys are `payload_file`, `delegate_target`, `missing_case`, `kind`, `prompt_prefix`, `value_path`, `options`, `attrs`, `match_mode`, and `prepare_expr`; policy-specific keys are `continue_rules`, `caller_value_expr`, `caller_field_specs`, `caller_rules`, `delegate_base_expr`, and `delegate_rules`
- `define-workflow-spec` expects a plain string `name` plus one workflow-spec quotation. The named spec is only available during the current expansion pass, which means callers should declare it in linked source such as `vm/common.vm`
- `extend-workflow-spec` expects plain string `base_name` and `name` values plus one quotation of override key/value pairs. Overrides replace existing keys from the base spec and can add new ones
- `use-workflow-spec` expects plain string `name`, `role`, and `policy` values. It fails expansion if the named workflow spec has not already been declared earlier in the linked program source
- `define-workflow-family` expects a plain string `name` plus one quotation of repeating `section_name section_contract` pairs. Each section contract must itself be a workflow-spec quotation. Use `shared` for fields that should merge into multiple role/policy sections
- `extend-workflow-family` expects plain string `base_name` and `name` values plus one quotation of repeating `section_name section_contract` pairs. Overrides replace full sections from the base family and can add new sections
- `use-workflow-family` expects plain string `name`, `role`, and `policy` values. It selects section `role.policy`, merges it over the optional `shared` section, and then expands through `workflow-spec`
- `define-choice-continue-spec` expects plain `name`, `payload_file`, `kind`, `prompt_prefix`, `value_path`, and `match_mode` syntax values plus quoted `options`, `attrs`, `prepare_expr`, and `rules`; it materializes the same named direct-router workflow spec that would otherwise be spelled out through `define-workflow-spec`
- `define-choice-answer-spec` expects plain `name`, `kind`, `prompt_prefix`, `value_path`, and `match_mode` syntax values plus quoted `options`, `attrs`, `prepare_expr`, and `delegate_rules`; it materializes a named delegate answer spec for later `use-workflow-spec`
- `define-choice-answer-family` expects plain `name`, `payload_file`, `delegate_target`, `kind`, `prompt_prefix`, `value_path`, and `match_mode` syntax values plus quoted `missing_case`, `caller_value_expr`, `options`, `attrs`, `prepare_expr`, and `delegate_rules`; it materializes paired `caller.answer` and `delegate.answer` sections for later `use-workflow-family`
- `define-choice-continue-answer-family` expects plain `name`, router-side `payload_file`, `kind`, `prompt_prefix`, `value_path`, `match_mode`, delegate-side `delegate_kind`, `delegate_prompt_prefix`, `delegate_value_path`, and `delegate_match_mode` syntax values plus quoted router `options`, `attrs`, `prepare_expr`, `continue_rules` and delegate `delegate_options`, `delegate_attrs`, `delegate_prepare_expr`, `delegate_rules`; it materializes paired `router.continue` and `delegate.answer` sections
- `define-choice-route-family` expects plain `name`, `payload_file`, `delegate_target`, `kind`, `prompt_prefix`, `value_path`, and `match_mode` syntax values plus quoted `missing_case`, `caller_field_specs`, `caller_value_expr`, `caller_rules`, `options`, `attrs`, `prepare_expr`, `delegate_base_expr`, and `delegate_rules`; it materializes paired `caller.route` and `delegate.route` sections
- `define-choice-finalize-family` expects plain `name`, `payload_file`, `delegate_target`, `kind`, `prompt_prefix`, `value_path`, and `match_mode` syntax values plus quoted `missing_case`, `caller_field_specs`, `caller_value_expr`, `options`, `attrs`, `prepare_expr`, `delegate_base_expr`, and `delegate_rules`; it materializes paired `caller.finalize` and `delegate.finalize` sections
- `continue-workflow-contract` expects one quotation of repeating key/value pairs. The current top-level contract keys are `payload_file`, `kind`, `prompt_prefix`, `value_path`, `options`, `attrs`, `match_mode`, `prepare_expr`, and `rules`, with optional `role: "router"` for explicitness
- `answer-workflow-contract` expects one quotation of repeating key/value pairs plus a required `role`. For `role: "caller"` it consumes `payload_file`, `delegate_target`, `missing_case`, and `value_expr`. For `role: "delegate"` it consumes `kind`, `prompt_prefix`, `value_path`, `options`, `attrs`, `match_mode`, `prepare_expr`, and `rules`
- `route-workflow-contract` expects one quotation of repeating key/value pairs plus a required `role`. For `role: "caller"` it consumes `payload_file`, `delegate_target`, `missing_case`, `field_specs`, `value_expr`, and `rules`. For `role: "delegate"` it consumes `kind`, `prompt_prefix`, `value_path`, `options`, `attrs`, `match_mode`, `prepare_expr`, `base_expr`, and `rules`
- `finalize-workflow-contract` expects one quotation of repeating key/value pairs plus a required `role`. For `role: "caller"` it consumes `payload_file`, `delegate_target`, `missing_case`, `field_specs`, and `value_expr`. For `role: "delegate"` it consumes `kind`, `prompt_prefix`, `value_path`, `options`, `attrs`, `match_mode`, `prepare_expr`, `base_expr`, and `rules`
- `normalized-return-flow` expects `missing_case`, `field_specs`, `value_expr`, and `rules` as quotations plus plain `output_mode`, `payload_file`, and `delegate_target` syntax values; it specializes `return-contract-flow` for the checked-in “load YAML, normalize payload, hand off, resume” family and is now the preferred caller-side surface when the run starts from a payload file
- `caller-answer-workflow` expects `missing_case` and `value_expr` as quotations plus plain `payload_file` and `delegate_target` syntax values; it is the lower-level role-specialized caller surface for plain returned-answer workflows and specializes `normalized-answer-workflow`
- `caller-route-workflow` expects `missing_case`, `field_specs`, `value_expr`, and `rules` as quotations plus plain `payload_file` and `delegate_target` syntax values; it is the lower-level role-specialized caller surface for resumed route workflows and specializes `normalized-route-workflow`
- `caller-finalize-workflow` expects `missing_case`, `field_specs`, and `value_expr` as quotations plus plain `payload_file` and `delegate_target` syntax values; it is the lower-level role-specialized caller surface for resumed finalization workflows and specializes `normalized-finalize-workflow`
- `normalized-answer-workflow` expects `missing_case` and `value_expr` as quotations plus plain `payload_file` and `delegate_target` syntax values; it specializes `normalized-return-flow` for caller-side plain returned-answer workflows under `caller-answer-workflow`
- `normalized-route-workflow` expects `missing_case`, `field_specs`, `value_expr`, and `rules` as quotations plus plain `payload_file` and `delegate_target` syntax values; it specializes `normalized-return-flow` for resumed route workflows under `caller-route-workflow`
- `normalized-finalize-workflow` expects `missing_case`, `field_specs`, and `value_expr` as quotations plus plain `payload_file` and `delegate_target` syntax values; it specializes `normalized-return-flow` for resumed finalization workflows under `caller-finalize-workflow`
- `project-fields` expects one quotation containing repeating `source_path shared_path default` triples; each source path is read through `get-in?`, each default may be `None` to preserve missing values, and `body` continues inline after the generated shared writes
- `returned-field-policy` expects `missing_case`, `field_specs`, `value_expr`, and `rules` as quotations plus a plain `mode` syntax value; it specializes `returned-policy` for declarative field-spec tables instead of projection quotations
- `return-field-policy-flow` expects `load_body`, `missing_case`, `field_specs`, `value_expr`, and `rules` as quotations plus plain `payload_file`, `delegate_target`, and `mode` syntax values; it specializes `return-flow` plus `returned-field-policy`
- `return-field-route-flow` expects `load_body`, `missing_case`, `field_specs`, `value_expr`, and `rules` as quotations plus plain `payload_file` and `delegate_target` syntax values; it fixes `mode` to `handoff`
- `return-field-finalize-flow` expects `load_body`, `missing_case`, `field_specs`, and `value_expr` as quotations plus plain `payload_file` and `delegate_target` syntax values; it fixes `mode` to `finalize`
- `project-shared` expects one quotation containing repeating `projection_expr shared_path` pairs; each projection expression must be a quotation and is evaluated against the same source value saved in a generated temporary local before `body` continues inline
- `returned-handoff-switch` expects `missing_case`, `projections`, `value_expr`, and `cases` as quotations; it specializes `returned-yaml` plus `project-shared` plus `handoff-switch` for caller-side structured-return routing
- `returned-finalize` expects `missing_case`, `projections`, and `value_expr` as quotations; it specializes `returned-yaml` plus `project-shared` plus `finalize-from` for caller-side structured-return finalization
- `returned-policy` expects `missing_case`, `projections`, `value_expr`, and `rules` as quotations plus a plain `mode` syntax value; use `handoff` or `route` to delegate through `returned-handoff-switch`, and `finalize` or `answer` to finalize through `returned-finalize`
- `return-handoff` uses the current standard return policy shape: `return_to_caller: true`, `context_mode: whole`, and `return_transition: continue`
- `return-delegate` expands directly to the “returned path present vs set return policy and hand off” shape for delegate pass-through callers
- `maybe-handoff` expects both `value_expr` and `missing_case` as quotations; it drops the `None` sentinel before `missing_case` runs and otherwise leaves the resolved agent on the stack for `handoff`
- `indexed-value` expects `list_expr`, `index_expr`, `missing_case`, and `body` as quotations; `body` receives the selected list item on the stack when the index resolves successfully
- `indexed-handoff-route` expects `list_expr`, `index_expr`, and `body` as quotations plus plain `missing_reason` and `fallback_agent` syntax values; it specializes `indexed-value` for the config-router pattern where missing indexed targets always map to a `route_reason` plus fallback handoff
- `returned-answer` expects both `missing_case` and `body` as quotations; unlike `returned-yaml`, it does not parse the returned answer before running `body`
- `returned-answer-policy` expects `missing_case` and `value_expr` as quotations; it specializes `returned-answer` plus `finalize-from` for caller-side plain returned-answer finalization
- `returned-yaml` expects both `missing_case` and `body` as quotations; the generated expansion parses the returned delegate answer with `yaml>` before it runs `body`
- `prompt-store` expects `request_expr` and `body` as quotations; after the prompt resolves it stores the selected value through `shared!?` at `value_path` and then runs `body` against that same selected value
- `choice-request` expects `prompt_expr` as a quotation plus `options` and `attrs` as quotations of plain literals; `options` must be repeating `id label value` triples and `attrs` must be repeating `key value` pairs
- `summary-choice-flow` expects plain `prompt_prefix`, `output_mode`, `kind`, `value_path`, and `match_mode` syntax values plus quoted `options`, `attrs`, `prepare_expr`, `base_expr`, and `rules`; it specializes `choice-flow` for the checked-in normalization family where the final prompt should be `prompt_prefix + normalized.summary`
- `delegate-answer-workflow` expects plain `kind`, `prompt_prefix`, `value_path`, and `match_mode` syntax values plus quoted `options`, `attrs`, `prepare_expr`, and `rules`; it is the lower-level role-specialized delegate surface for normalized-summary plain returned answers and specializes `summary-answer-workflow`
- `delegate-structured-workflow` expects plain `kind`, `prompt_prefix`, `value_path`, and `match_mode` syntax values plus quoted `options`, `attrs`, `prepare_expr`, `base_expr`, and `rules`; it is the lower-level role-specialized delegate surface for normalized-summary structured YAML decisions and specializes `summary-structured-workflow`
- `summary-answer-workflow` expects plain `kind`, `prompt_prefix`, `value_path`, and `match_mode` syntax values plus quoted `options`, `attrs`, `prepare_expr`, and `rules`; it specializes `summary-choice-flow` for delegates that should return a plain answer under `delegate-answer-workflow`
- `summary-structured-workflow` expects plain `kind`, `prompt_prefix`, `value_path`, and `match_mode` syntax values plus quoted `options`, `attrs`, `prepare_expr`, `base_expr`, and `rules`; it specializes `summary-choice-flow` for delegates that should return structured YAML decisions under `delegate-structured-workflow`
- `normalized-choice-router` expects plain `payload_file`, `output_mode`, `kind`, `prompt_prefix`, `value_path`, and `match_mode` syntax values plus quoted `options`, `attrs`, `prepare_expr`, `base_expr`, and `rules`; it specializes the recurring “load payload, normalize, ask a structured choice, continue” authoring pattern and is now the lower-level direct-router surface under `router-continue-workflow`
- `router-continue-workflow` expects plain `payload_file`, `kind`, `prompt_prefix`, `value_path`, and `match_mode` syntax values plus quoted `options`, `attrs`, `prepare_expr`, and `rules`; it is the lower-level role-specialized router surface for checked-in normalization examples and specializes `normalized-continue-workflow`
- `normalized-continue-workflow` expects plain `payload_file`, `kind`, `prompt_prefix`, `value_path`, and `match_mode` syntax values plus quoted `options`, `attrs`, `prepare_expr`, and `rules`; it specializes `normalized-choice-router` for direct continuation workflows and is now the lower-level workflow-specialized router surface under `router-continue-workflow`
- `choice-flow` expects the same syntax surface as `choice-contract`; use `continue` for direct router continuation or handoff branches, `answer` for plain returned text, and `structured` for declarative returned field specs so one authored shape can cover direct interaction flows and delegate decisions
- `choice-policy` expects `prompt_expr`, `options`, `attrs`, `prepare_expr`, and `rules` as quotations plus plain `kind`, `value_path`, and `match_mode` syntax values; use it when the request should be declared from a choice table instead of loading a prebuilt request mapping
- `prompt-store-policy` expects `request_expr`, `prepare_expr`, and `rules` as quotations plus a plain `match_mode` syntax value; use `exact` or `switch` for ordinary `switch` routing and `contains` or `membership` for checklist-style `contains?` routing
- `prompt-return-policy` expects `request_expr`, `prepare_expr`, and `rules` as quotations plus a plain `match_mode` syntax value; use `exact` or `switch` for exact-value decision tables and `contains` or `membership` when the returned answer should come from checklist membership or a default multi-select formatter
- `prompt-return-yaml-policy` expects `request_expr`, `prepare_expr`, and `rules` as quotations plus a plain `match_mode` syntax value; use it when branch bodies should return mapping/list data and the delegate should emit YAML only at the answer boundary
- `prompt-return-merge-policy` expects `request_expr`, `prepare_expr`, `base_expr`, and `rules` as quotations plus a plain `match_mode` syntax value; use it when all returned decisions share a common mapping fragment such as delegate metadata
- `prompt-decision` expects `request_expr`, `prepare_expr`, `base_expr`, and `rules` as quotations plus plain `output_mode`, `value_path`, and `match_mode` syntax values; use `answer`, `yaml`, or `yaml-merge` to pick the delegate output contract without changing the surrounding prompt authoring shape
- `choice-decision` expects `prompt_expr`, `options`, `attrs`, `prepare_expr`, `base_expr`, and `rules` as quotations plus plain `output_mode`, `kind`, `value_path`, and `match_mode` syntax values; use it when the delegate should declare both the request shape and the returned-output contract from one authored surface
- `choice-contract` expects the same syntax surface as `choice-decision`; use `answer` for plain returned text and `structured` for declarative returned field specs so one top-level authored form can cover both simple and machine-readable delegate decisions
- `record-fields` expects `base_expr` as a quotation that leaves a mapping plus `field_specs` as a quotation of repeating `path value` pairs; each value may be a literal or a quotation, and nested paths are written through `set-in`
- `choice-structured-decision` expects `prompt_expr`, `options`, `attrs`, `prepare_expr`, `base_expr`, and `rules` as quotations plus plain `kind`, `value_path`, and `match_mode` syntax values; each rule body must be a quotation of repeating `path value` pairs, and the generated delegate always emits YAML after building the returned mapping from `base_expr` plus those field specs
- `prompt-store-switch` expects `request_expr` and `cases` as quotations; after the prompt resolves it stores the selected value through `shared!?` at `value_path` and then switches on that same selected value
- `prompt-store-contains-switch` expects `request_expr`, `prepare_expr`, and `rules` as quotations; after the prompt resolves it stores the selected value through `shared!?` at `value_path`, runs `prepare_expr`, and then checks the selected list for each rule needle in order until one branch matches, with `"default"` as the final fallback needle
- `ask-from` expects `question_expr` as a quotation; use it when the question text needs multi-step concatenation before `ask-user`
- `prompt-store-text` expects `question_expr` and `body` as quotations; after the text prompt resolves it stores the reply with `shared!?` at `value_path` and then runs `body` against that same reply value
- `delegate-return` remains available as the lower-level pass-through form when callers need a custom return-policy setup

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

Persist a reason and hand off immediately:

```text
"missing_route" "route_reason" "router.fallback" shared-handoff
```

This is the built-in shorthand for the recurring config-router fallback shape where the branch only records a shared status or reason and then delegates.

Collect a checklist selection, store it, prepare derived text once, and branch by membership:

```text
[
  common.checklist-approve-delegate-review
  dup "prompt" "Choose actions for " "normalized.summary" shared@ concat dict-set
]
"normalized.selected_actions"
[ common.format-selected-actions ]
[
  "delegate" [ "router.delegate_route" handoff ]
  "approve" [ "router.approve_route" handoff ]
  "default" [ "router.review_route" handoff ]
]
prompt-store-contains-switch
```

This is the built-in shorthand for checklist-style flows that used to stack `prompt-interaction`, `shared!?`, a formatting helper, and repeated `contains?` branches by hand.

Unify exact-match and membership routing behind one prompt policy surface:

```text
[
  common.buttons-approve-delegate-deny
  dup "prompt" "Choose next step for " "normalized.summary" shared@ concat dict-set
]
"normalized.choice"
"exact"
[ ]
[
  "approve" [ "router.approve" handoff ]
  "default" [ "router.review" handoff ]
]
prompt-store-policy
```

```text
[
  common.checklist-approve-delegate-review
  dup "prompt" "Choose actions for " "normalized.summary" shared@ concat dict-set
]
"normalized.selected_actions"
"contains"
[ common.format-selected-actions ]
[
  "delegate" [ "router.delegate" handoff ]
  "default" [ "router.review" handoff ]
]
prompt-store-policy
```

`prompt-store-policy` is the lower-level request-aware form when the request mapping already exists. Prefer `define-choice-continue-spec`, `define-choice-answer-spec`, `define-choice-answer-family`, `define-choice-continue-answer-family`, `define-choice-route-family`, and `define-choice-finalize-family` for the checked-in direct continuation and caller/delegate workflow families, `summary-choice-flow` when only the normalized-summary prompt needs abstraction, and plain `choice-flow` when the prompt logic is fully custom.

Return directly from a prompt-driven decision table:

```text
[
  common.buttons-approve-reject
  dup "prompt" "Choose delegate action for " "normalized.summary" shared@ concat dict-set
]
"normalized.delegate_choice"
"exact"
[ ]
[
  "approve" [ "delegate approved " "normalized.summary" shared@ concat ]
  "default" [ "delegate rejected " "normalized.summary" shared@ concat ]
]
prompt-return-policy
```

`prompt-return-policy` is the higher-level built-in when a delegate should collect a structured choice and immediately produce the returned answer or YAML payload from a declarative decision table.

Declare the delegate prompt, option table, and output contract from one surface:

```text
"answer"
"buttons"
[ "Choose delegate action for " "normalized.summary" shared@ concat ]
"normalized.delegate_choice"
[
  "approve" "Approve" "approve"
  "reject" "Reject" "reject"
]
[ ]
"exact"
[ ]
[ ]
[
  "approve" [ "delegate approved " "normalized.summary" shared@ concat ]
  "default" [ "delegate rejected " "normalized.summary" shared@ concat ]
]
choice-decision
```

```text
"yaml-merge"
"radio"
[ "Choose nested route for " "normalized.summary" shared@ concat ]
"normalized.delegate_choice"
[
  "approve" "Approve" "approve"
  "review" "Review" "review"
]
[ ]
"exact"
[ ]
[ "{}" yaml> "delegate" "meta.source" set-in ]
[
  "approve" [ "{}" yaml> "approve" "decision.route" set-in "approved by delegate" "decision.note" set-in ]
  "default" [ "{}" yaml> "review" "decision.route" set-in ]
]
choice-decision
```

`choice-decision` is the lower-level delegate-side surface underneath `choice-contract`, `choice-flow`, `summary-choice-flow`, inline `workflow-spec`, named workflow-spec bindings, and the lower-level workflow contracts. Keep it for cases where the request should still come from a choice table but you want direct access to the raw delegate output-contract split.

Build one returned mapping from declarative field specs:

```text
[ "{}" yaml> "delegate" "meta.source" set-in ]
[
  "decision.route" "approve"
  "decision.note" "approved by delegate"
]
record-fields
```

Declare a structured delegate decision from one choice table and one returned-field table:

```text
"radio"
[ "Choose nested route for " "normalized.summary" shared@ concat ]
"normalized.delegate_choice"
[
  "approve" "Approve" "approve"
  "review" "Review" "review"
]
[ ]
"exact"
[ ]
[ "{}" yaml> "delegate" "meta.source" set-in ]
[
  "approve" [ "decision.route" "approve" "decision.note" "approved by delegate" ]
  "default" [ "decision.route" "review" ]
]
choice-structured-decision
```

`choice-structured-decision` is the lower-level structured delegate surface underneath `choice-contract`, `choice-flow`, `summary-choice-flow`, inline `workflow-spec`, named workflow-spec bindings, and the lower-level structured workflow contracts. Use it when the request should still come from a choice table but you want direct access to the field-spec-only structured branch form.

Declare both direct router choices and delegate-side decisions from one top-level choice workflow surface:

```text
"continue"
"buttons"
[ "Choose next step for " "normalized.summary" shared@ concat ]
"normalized.choice"
[
  "approve" "Approve" "approve"
  "delegate" "Delegate" "delegate"
  "deny" "Deny" "deny"
]
[ ]
"exact"
[ ]
[ ]
[
  "approve" [ "Approved " "normalized.summary" shared@ concat answer ]
  "default" [ "Denied " "normalized.summary" shared@ concat answer ]
]
choice-flow
```

```text
"structured"
"radio"
[ "Choose route for " "normalized.summary" shared@ concat ]
"normalized.delegate_choice"
[
  "approve" "Approve" "approve"
  "review" "Review" "review"
]
[ ]
"exact"
[ ]
[ "{}" yaml> "delegate" "meta.source" set-in ]
[
  "approve" [ "decision.route" "approve" "decision.note" "approved by delegate" ]
  "default" [ "decision.route" "review" ]
]
choice-flow
```

Prefer the specialized choice-workflow builders first: `define-choice-continue-spec` for direct normalized continuation, `define-choice-answer-spec` for a single delegate answer contract, `define-choice-answer-family` for paired caller/delegate answer workflows, `define-choice-continue-answer-family` for hybrid router/delegate pipelines, `define-choice-route-family` for structured resumed routing, and `define-choice-finalize-family` for structured resumed finalization. Keep `define-workflow-family` plus `use-workflow-family` as the generic compile-time family layer when a workflow does not fit those higher-level builders, and `define-workflow-spec` plus `use-workflow-spec` as the generic single-policy layer. Keep inline `workflow-spec` as the lower-level escape hatch when a spec really is local to one file. Keep `continue-workflow-contract`, `answer-workflow-contract`, `route-workflow-contract`, and `finalize-workflow-contract` as lower-level contract adapters underneath that layer. Keep `router-continue-workflow`, `delegate-answer-workflow`, `delegate-structured-workflow`, `caller-answer-workflow`, `caller-route-workflow`, and `caller-finalize-workflow` as lower-level role-and-policy-specialized forms under that layer. Keep `normalized-continue-workflow`, `summary-answer-workflow`, `summary-structured-workflow`, `normalized-answer-workflow`, `normalized-route-workflow`, and `normalized-finalize-workflow` as lower-level workflow-specialized forms under that. Use the lower-level `summary-choice-flow` and `normalized-return-flow` forms when you still want one generic normalized choice or return macro, and keep plain `choice-flow`, `choice-policy`, `choice-contract`, `choice-decision`, and `choice-structured-decision` as escape hatches for non-normalized or fully custom prompt logic.

Collect a structured choice and return YAML from mapping data instead of hand-authored YAML strings:

```text
[
  common.radio-approve-escalate-review
  dup "prompt" "Choose final route for " "normalized.summary" shared@ concat dict-set
]
"normalized.delegate_choice"
"exact"
[ ]
[
  "approve" [ "{}" yaml> "approve" "route" dict-set "approved by delegate" "note" dict-set ]
  "default" [ "{}" yaml> "review" "route" dict-set "review requested by delegate" "note" dict-set ]
]
prompt-return-yaml-policy
```

This is the higher-level built-in when a delegate should work with returned machine-readable data as mappings/lists inside the VM and only serialize through `yaml<` at the answer boundary.

Collect a structured choice and merge common returned metadata with the decision-specific mapping:

```text
[
  common.radio-approve-escalate-review
  dup "prompt" "Choose nested route for " "normalized.summary" shared@ concat dict-set
]
"normalized.delegate_choice"
"exact"
[ ]
[ "{}" yaml> "delegate" "meta.source" set-in ]
[
  "approve" [ "{}" yaml> "approve" "decision.route" set-in "approved by delegate" "decision.note" set-in ]
  "default" [ "{}" yaml> "review" "decision.route" set-in ]
]
prompt-return-merge-policy
```

This is the higher-level built-in when a delegate should construct decision-specific nested mappings and merge them with shared metadata before the final YAML serialization step.

Validate a schema envelope and route on the normalized value:

```text
[
  [ dup "value" dict-get? dup "config" store-set drop ]
  [
    [ "{enabled: true, route: $target}" yaml> ] [ "match.target" shared@ handoff ]
    [ "{enabled: false}" yaml> ] [ "fallback.agent" handoff ]
    _
    [ "invalid" "route_reason" shared! "fallback.agent" handoff ]
  ]
  [ drop "invalid" "route_reason" shared! "fallback.agent" handoff ]
  validated-match
]
```

This is the built-in shorthand for the common `dup "success" dict-get? ... "value" dict-get? ... match ... if` shape. Checked-in consumers include `examples/stackvm_config_router_example/` and `examples/stackvm_nested_router_example/`.

Store schema errors and route in one step:

```text
"config_errors"
"config"
[
  [ "{enabled: true, route: $target}" yaml> ] [ "match.target" shared@ handoff ]
  [ "{enabled: false}" yaml> ] [ "fallback.agent" handoff ]
  _
  [ "invalid" "route_reason" shared! "fallback.agent" handoff ]
]
[ drop "invalid" "route_reason" shared! "fallback.agent" handoff ]
schema-route
```

This is the built-in shorthand for the recurring config-router pattern: persist `errors`, optionally persist the normalized `value`, and then delegate to `validated-match`.

Expand rule triplets into band-setting handoff branches:

```text
[
  [ "normalized.total" shared@ 10 >= ] "high" "router.high_route"
  [ "normalized.total" shared@ 5 >= ] "review" "router.review_route"
  [ True ] "low" "router.low_route"
]
"normalized.band"
handoff-rules
```

Route one computed key through handoff-only switch branches:

```text
[ "normalized.final_route" shared@ ]
[
  "approve" "router.approve_route"
  "escalate" "router.escalate_route"
  "default" "router.review_route"
]
handoff-switch
```

Project multiple values from one mapping into shared state before continuing:

```text
[
  [ "route" dict-get ] "normalized.final_route"
  [ "note" dict-get ] "normalized.delegate_note"
]
[
  "normalized.final_route" shared@ answer
]
project-shared
```

This is the built-in shorthand for structured-return caller flows that used to repeat `dup ... dict-get ... shared!? drop` or `get-in?` plus defaulting logic for several fields before routing or finalizing.

Project multiple values from one returned mapping into shared state from declarative field specs:

```text
[
  "decision.route" "normalized.final_route" "review"
  "decision.note" "normalized.delegate_note" "no note"
  "meta.source" "normalized.delegate_source" "delegate"
]
[
  "normalized.final_route" shared@ answer
]
project-fields
```

This is the higher-level shorthand above `project-shared` when the authored surface should describe field contracts directly instead of embedding `dict-get` or `get-in?` quotations inline.

This is the built-in shorthand for the recurring aggregate-router pattern: keep the routing table declarative, store the chosen band once, and let the generated `cond` branches handle the repeated `shared!` plus `handoff` action shape.

Parse a returned YAML answer before caller-side routing or finalization:

```text
[ "Delegate returned without an answer." answer ]
[
  dup "route" dict-get dup "normalized.final_route" shared!? drop
  "normalized.final_route" shared@
  [
    "approve" [ "router.approve_route" handoff ]
    "default" [ "router.review_route" handoff ]
  ] switch
]
returned-yaml
```

This is the built-in shorthand for the recurring caller-side structured-return pattern: read `last_delegated_result.answer`, handle the missing-answer branch once, parse the YAML answer, and then route or finalize from the parsed value.

Parse a returned YAML decision, project fields, and route by handoff table:

```text
[ "Delegate returned without an answer." answer ]
[
  [ "route" dict-get ] "normalized.final_route"
  [ "note" dict-get ] "normalized.delegate_note"
]
[ "normalized.final_route" shared@ ]
[
  "approve" "router.approve_route"
  "default" "router.review_route"
]
returned-handoff-switch
```

Parse a returned YAML decision, project fields, and finalize from one composed value:

```text
[ "Delegate returned without an answer." answer ]
[
  [ "mode" dict-get ] "normalized.delegate_mode"
  [ "message" dict-get ] "normalized.delegate_message"
]
[ "finalized: " "normalized.delegate_mode" shared@ concat ]
returned-finalize
```

Set the standard return policy and hand off:

```text
"router.delegate" return-handoff
```

This is the built-in shorthand for the recurring `pending_handoff_policy` plus `handoff` setup used by return-to-caller caller flows.

Set the standard return policy and pass a returned value straight through:

```text
"router.delegate"
"last_delegated_result.answer"
return-delegate
```

This is the built-in shorthand for the recurring caller pattern that used to combine return-policy setup with `delegate-return`.

Resume a return-to-caller flow from one declarative caller policy:

```text
"prompt_return_payload.yaml"
[
  common.payload-data "payload" store-set
  "payload" store-get common.normalize-item-titles
  "payload" store-get common.store-normalized-source
  common.store-normalized-summary
]
"router.confirm_delegate"
[
  [ drop "Delegate returned without an answer." answer ]
  [ "Caller received delegate decision: " swap concat ]
  returned-answer-policy
]
return-flow
```

This is the built-in shorthand for the recurring caller-side protocol that used to repeat `last_delegated_result` branching, `stdlib.io.read-yaml-file-once`, generic tool-load failure handling, and `return-handoff`.

Resume a return-to-caller flow and finalize from a plain returned answer in one step:

```text
"prompt_return_payload.yaml"
[
  common.payload-data "payload" store-set
  "payload" store-get common.normalize-item-titles
  "payload" store-get common.store-normalized-source
  common.store-normalized-summary
]
"router.confirm_delegate"
[ drop "Delegate returned without an answer." answer ]
[ "Caller received delegate decision: " swap concat ]
return-answer-flow
```

This is the higher-level shorthand above `return-flow` plus `returned-answer-policy` for plain prompt-return caller flows.

Resume a return-to-caller flow and apply a structured returned-value policy in one step:

```text
"structured_return_payload.yaml"
[
  common.payload-data "payload" store-set
  "payload" store-get common.normalize-item-titles
  "payload" store-get common.store-normalized-source
  common.store-normalized-summary
]
"router.confirm_delegate"
[ "Delegate returned without an answer." answer ]
[
  [ "route" dict-get ] "normalized.final_route"
  [ "note" dict-get ] "normalized.delegate_note"
]
"handoff"
[ "normalized.final_route" shared@ ]
[
  "approve" "router.approve_route"
  "default" "router.review_route"
]
return-policy-flow
```

This is the higher-level shorthand above `return-flow` plus `returned-policy` for structured-return caller flows.

Resume a return-to-caller flow and route from declarative returned-field specs in one step:

```text
"structured_return_payload.yaml"
[
  common.payload-data "payload" store-set
  "payload" store-get common.normalize-item-titles
  "payload" store-get common.store-normalized-source
  common.store-normalized-summary
]
"router.confirm_delegate"
[ "Delegate returned without an answer." answer ]
[
  "route" "normalized.final_route" None
  "note" "normalized.delegate_note" None
]
[ "normalized.final_route" shared@ ]
[
  "approve" "router.approve_route"
  "default" "router.review_route"
]
return-field-route-flow
```

Resume a return-to-caller flow and finalize from declarative returned-field specs in one step:

```text
"structured_finalize_payload.yaml"
[
  common.payload-data "payload" store-set
  "payload" store-get common.normalize-item-titles
  "payload" store-get common.store-normalized-source
  common.store-normalized-summary
]
"router.confirm_delegate"
[ "Delegate returned without an answer." answer ]
[
  "mode" "normalized.delegate_mode" None
  "message" "normalized.delegate_message" None
]
[
  "finalized: "
  "normalized.delegate_mode" shared@ concat
]
return-field-finalize-flow
```

These field-spec forms are now the preferred authored surface for structured-return caller examples. They keep the returned-data contract visible in one compact table and leave quotation-based `returned-policy` authoring as the lower-level escape hatch.

Hand off when an optional agent exists, otherwise run a fallback branch:

```text
[ "routes" store-get 0 list-get? ]
[ "missing_route" "route_reason" shared! "router.fallback" handoff ]
maybe-handoff
```

This is the built-in shorthand for the recurring “lookup maybe returned an agent, otherwise mark a route reason and fall back” pattern used by the config-driven routers.

Select one indexed list value and branch once on absence:

```text
[ "routes" store-get ]
[ "selected_index" store-get ]
[ "missing_route" "route_reason" "router.fallback" shared-handoff ]
[ handoff ]
indexed-value
```

This is the built-in shorthand for the recurring config-router pattern that used to repeat `list-get? dup none? ... if` around selected route or target values.

Select one indexed route target with a standard route-reason fallback:

```text
[ "routes" store-get ]
[ "selected_index" store-get ]
"missing_route"
"router.fallback"
[ handoff ]
indexed-handoff-route
```

This is the built-in shorthand for config-router branches that combine indexed selection with the standard `route_reason` plus fallback handoff contract.

Read a returned plain-text answer before caller-side finalization:

```text
[ "Delegate returned without an answer." answer ]
[ [ "Caller received: " swap concat ] finalize-from ]
returned-answer
```

This is the built-in shorthand for the recurring plain returned-answer pattern used by the prompt-return and checklist-return caller flows.

Read a returned plain-text answer and finalize from one composed value expression:

```text
[ drop "Delegate returned without an answer." answer ]
[ "Caller received: " swap concat ]
returned-answer-policy
```

This is the higher-level shorthand above `returned-answer` plus `finalize-from` for prompt-return and checklist-return caller flows.

Store a structured prompt selection and keep executing:

```text
[
  "{kind: radio, prompt: Choose mode, options: [{id: approve, label: Approve, value: approve}]}" yaml>
]
"normalized.choice"
[ "Selected " swap concat answer ]
prompt-store
```

This is the built-in shorthand for the recurring direct `prompt-interaction` pattern used by radio-style routers and structured-return delegates: present a structured choice, persist the selected value once, and keep executing from that same value.

Store a structured prompt selection and route through a switch table:

```text
[
  "{kind: radio, prompt: Choose mode, options: [{id: approve, label: Approve, value: approve}]}" yaml>
]
"normalized.choice"
[
  "approve" [ "router.approve" handoff ]
  "default" [ "router.review" handoff ]
]
prompt-store-switch
```

This is the built-in shorthand for the recurring direct structured-interaction pattern where the selected value should be persisted and then routed immediately through an exact-value case table.

Compute a question at runtime before `ask-user`:

```text
[ "Proceed with " "normalized.summary" shared@ concat "?" concat ]
ask-from
```

This is the built-in shorthand for direct question flows that want to derive the prompt text from normalized shared state instead of embedding a literal string.

Collect text input, store it, and keep executing:

```text
[ "Proceed with " "normalized.summary" shared@ concat "?" concat ]
"normalized.reply"
[ bool> ]
prompt-store-text
```

This is the built-in shorthand for the recurring bridged text-input pattern: compute the prompt at runtime, collect a text reply through `prompt-user`, persist it once, and continue from that same reply value.

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
- `last_vm_analysis`: static analysis summary for the expanded executable AST plus the configured entry word when one is present
- `last_vm_diagnostics`: non-fatal static diagnostics collected from that analysis, such as stack-underflow and illegal combinator-child-effect warnings

The `/stackvm inspect` command now prints that same warning-plus-diagnostics view together with inferred effect kinds, maximum observed stack depth during static analysis, the final guaranteed minimum stack depth after analysis, and the final stack shape.

The `/stackvm explain` command now builds on the same compile payload and also prints the recorded macro expansion trace, expansion frames, analysis decisions from `last_vm_analysis.analysis_decisions`, scope summaries from `last_vm_analysis.scope_summaries`, a scoped static shape-flow trace from `last_vm_analysis.shape_flow`, inferred user-word contracts from `last_vm_analysis.word_metadata_summary`, each helper's `output_shape`, and the program's final stack shape.

When `/stackvm debug` tracing is enabled, the runtime `vm_trace` entries now carry both structural runtime information and the same two source layers when the VM can preserve them through execution:

- `scope`: the current runtime execution region, such as `main`, `main > word:main`, `main > while:body`, or a combinator child scope
- `depth`: the nesting depth of that runtime scope
- `stack_before`: the stack snapshot immediately before the traced step
- `stack_delta`: a compact `{depth_change, popped, pushed}` summary relative to the previous stack
- `stack_after`: the stack snapshot immediately after the traced step
- `vm_trace_decisions`: compact runtime control-flow decisions such as selected `if` branches, matched `switch`/`cond`/`match` paths, loop continue or stop outcomes, and fallback activation or primary success
- `vm_trace_scope_summaries`: compact per-scope summaries derived from the same runtime nesting model, including input stack, output stack, net `stack_delta`, and whether the scope preserved stack depth

- `location`: the executed node's location in the serialized expanded StackVM program
- `authored_location`: the executed node's authored source location when that expanded node can be traced back to original source or replayed helper-body source

That means runtime debug traces are no longer just flat stack snapshots. They now preserve nested execution scopes, expose a compact decision layer plus a per-scope summary layer, show how each step changed the stack, and can point back to expanded source and, for many macro-generated or replayed helper steps, back to the authored source site as well.

Each inferred user-word contract now includes:

- `pops`
- `pushes`
- `effect_kind`
- `output_shape`

`output_shape` is the analyzer's current best-effort summary of the kinds of stack values the helper leaves behind. It can now preserve concrete result kinds for a small set of obvious built-ins, such as `["int"]` for helpers built around `len`, `["bool"]` for helpers built around `empty?` or comparisons, and `["str"]` for helpers built around `concat`, `join`, or `str>`. Helpers still fall back to `["unknown"]` when the analyzer does not have a more specific shape at contract-inference time.

When the analyzer later evaluates a call site for a user-defined helper, it now replays that helper's quotation against the caller's current abstract stack. That means call-site stack-depth and branch precision can improve even when the helper's own summarized `output_shape` remains generic.

The analysis summary also now carries:

- `final_stack_shape`: the analyzer's best-effort list of final stack value kinds after the expanded program and configured entry word have been analyzed
- `analysis_decisions`: higher-level decisions the analyzer made while merging or degrading precision, including explicit optional no-match paths and conservative loop merges
- `scope_summaries`: structured summaries for analyzed regions and merge points, including each region's input/output stack shapes and each branch merge's branch output shapes and merged result
- `shape_flow`: an ordered static trace of literals, quotations, and words together with the analyzer's post-step stack shape

Each `shape_flow` item now also carries a `scope` string. The analyzer uses that scope to separate top-level `main` execution from nested regions such as user-word calls, `while` condition/body quotations, `if` branches, `cond` conditions/actions, `switch` cases, and combinator child quotations. The `/stackvm explain` command groups the trace by those scopes so nested control-flow and helper boundaries are explicit. When a traced word originated from macro expansion and the originating span is known, the step also carries `authored_location`. That authored span is now more precise for direct parameter substitution and `unquote` or `unquote-splice` expansion than it used to be. Replayed helper-body steps can now also fall back to the helper definition body's authored span even when there is no matching token in the serialized expanded source, so nested `word:...` traces retain useful source coordinates inside helper bodies.

`analysis_decisions` is the most compact layer. It records why the analyzer chose a particular merge strategy, such as keeping an optional no-match path for `switch` or `cond`, preserving a `while` loop precisely because its shape stayed stable, or falling back to a conservative loop merge when shape changed. When the originating word can be mapped back into the expanded program, those decisions now also carry a `location` field so `/stackvm explain` can point directly at the relevant site. When the same expanded word can be traced back to a macro call site, the decision also carries `authored_location`.

`scope_summaries` complements that decision layer with concrete outcomes. Region entries show the input and output stack shapes, effect kinds, diagnostic counts, unknown output counts, and whether the scope preserved the incoming stack shape. Merge entries show the branch output shapes the analyzer saw, the final merged stack shape that flowed back into the parent scope, and the merge reason and precision classification. Like diagnostics and decisions, scope summaries now include a `location` field when the analyzer can attribute that scope to a concrete word in the expanded source, and `authored_location` when that expanded word came from a known macro call site.

For replayed user-defined helpers, region summaries may also carry `definition_location`. That lets `/stackvm explain` show both where the helper was called and where the helper body was originally defined.

Those summaries now appear in the StackVM CLI inspect/check/explain surfaces, and `final_stack_shape` also appears in the run/debug summary path.

For literal `yaml>` inputs, the analyzer can now carry enough structure to infer more specific results through `dict-get`, `dict-get?`, `list-get`, `list-get?`, `get-in`, and `get-in?` when the accessed fields or indexes are statically known.

When the analyzer can map a diagnostic back onto the serialized expanded program, each diagnostic now also carries `location` and `span` fields with line and column coordinates for the relevant word in the expanded StackVM source. When the same expanded word came from a macro call site and that source span is known, diagnostics also carry `authored_location` and `authored_span`. For replayed helper analysis, diagnostics can also fall back to the current helper-body AST span when no expanded-source token exists, so helper-local warnings still point at authored helper code.

The current analyzer also models the “no branch matched” path for `switch` without a `"default"` case, for `cond` without an unconditional `True` case, and for `match` without a wildcard `_` case. For `reduce`, it now warns when the child quotation appears to leave more than one guaranteed stack value instead of exactly one next accumulator.

For `while`, the analyzer still stays conservative in general, but it now suppresses that warning when both the condition quotation and the body quotation appear to preserve the incoming stack shape. That makes simple accumulator-style loops report a more accurate final minimum stack depth.

The same child-effect diagnostics used for `parallel-map` and `reduce` now also apply to the Phase 2 collection operators `map`, `filter`, `find`, `any?`, and `all?`. In the current implementation those words are treated as pure data operators with isolated child VMs, so `/stackvm inspect`, `/stackvm check`, and `/stackvm explain` warn when their child quotations may emit tool, prompt, handoff, final-answer, or other runtime effects.

Static analysis now also reports host-surface dependencies separately from effect kinds. The current payload includes:

- `host_surfaces_used`: which non-core host surfaces the program touches
- `pocketcoder_host_words_used`: the specific PocketCoder-only host words used by the analyzed program
- `standalone_script_compatible`: whether the analyzed program stays within the current standalone script host surface

This lets the CLI explain why a script stays on the lightweight standalone adapter or falls back to the PocketCoder runtime path.

`word_metadata_summary` now also carries `definition_location` for user-defined words when the helper definition can be mapped back to authored source. The explain view prints that beside each inferred helper contract.

The current `match` implementation is now part of the runtime surface. It accepts the same case/action pair quotation shape used by `switch` and `cond`, but each case may be a literal, the wildcard `_`, or a quotation that leaves a recursive dict/list pattern value. Strings beginning with `$` inside that pattern value bind the matched sub-value, `"$name:type"` adds a type constraint to that binding, list patterns may end with `$*name` to capture the remaining tail, dict patterns may include `$rest` to capture unmatched keys, and repeated bindings must stay consistent within the same pattern. Successful bindings are written into shared state under both `match` and `match.<name>`.

Schema-aware data words are also now part of the current runtime surface:

- `schema-check` validates a value against a schema and returns `{success, value, errors}` without rewriting the value
- `schema-apply` validates, coerces supported primitive types, applies declared defaults, and returns the same `{success, value, errors}` envelope

The current StackVM schema subset is intentionally aligned with the repo's existing command-schema model: `type`, `properties`, `required`, `items`, `default`, and `enum`, with primitive support for `string`, `boolean`, `integer`, and `number`.

Each `expansion_frames` entry now records the expanded macro name, whether it was built-in, expansion depth, the macro call-site location when known, the macro definition location when known, the parent macro that generated the current expansion when applicable, serialized syntax arguments, and the immediate expanded form.

Macro expansion failures retain an ordered macro trace so nested failures identify the expansion path.

## Current Limitations

Current macro support is intentionally limited:

- there is no richer compile-time evaluator beyond syntax substitution and limited compile forms
- hygiene is limited to generated symbol names from `gensym`
- macros expand before runtime host words execute; macros do not run tools, prompts, handoffs, or answers during expansion

Current diagnostics still have limits:

- expansion frames track source locations for parsed source forms and macro definitions, and analyzer output now threads those spans far enough to surface `authored_location` on many generated diagnostics, decisions, summaries, and flow steps
- direct parameter substitution plus `unquote` and `unquote-splice` now preserve argument-origin spans into the expanded AST, so many generated nodes point back to the authored argument site rather than only the macro invocation site
- nested generated forms still do not have a fully precise per-node origin in every case; some regions still inherit the parent macro call-site when no more specific span is available

## Example References

- `examples/stackvm_tool_normalize_example/`: built-in `tool-once`
- `examples/stackvm_parallel_tool_map_example/`: built-in `tool-once` around tool-first fan-out
- `examples/stackvm_reduce_tool_example/`: built-in `tool-once` around tool-first fan-in
- `examples/stackvm_threshold_router_example/`: built-in `tool-once` plus aggregate routing
- `examples/stackvm_buttons_example/`: built-in `tool-once` plus `prompt-route`
- `examples/stackvm_delegate_return_example/`: built-in `tool-once` plus `delegate-return`
- `examples/stackvm_macro_authoring_example/`: user-authored `defmacro`, `syntax-quote`, `unquote`, and `unquote-splice`
