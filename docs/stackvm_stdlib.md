# StackVM Standard Library

This document is the canonical reference for the checked-in reusable StackVM module surface.

Use this together with `stackvm_cookbook.md` for authoring patterns, `stackvm_macros.md` for compile-time forms, and `architecture.md` for flow loading and search-root behavior.

## Location And Loading

The current shared StackVM standard-library modules live under workspace-root `vm/stdlib/`.

The current stdlib package metadata lives beside those modules in `vm/stdlib/stdlib.yaml`.

Author-facing `vm_modules` entries can now use the manifest-backed package names directly, for example `stdlib.io` or `stdlib.prompt`, instead of file-style refs like `vm/stdlib/io`. File-style refs still work for compatibility.

Flows and scripts can load those modules with ordinary `vm_modules` entries such as:

```yaml
vm_modules:
  - stdlib.config
  - vm/common
  - vm/router
```

Current lookup behavior:

- standalone scripts already search the workspace root when resolving VM refs
- VM-backed flows now also include `workspace_root` in their StackVM source search roots
- checked-in integration tests copy the repo's shared `vm/` directory into the temp workspace so example flows exercise the same package layout

This means a shared stdlib module can now be loaded once from the workspace root instead of being copied into each example namespace.

## Package Metadata

The checked-in stdlib now has one canonical manifest file:

- `vm/stdlib/stdlib.yaml`

Current manifest fields:

- `package`: current package name, currently `stackvm-stdlib`
- `version`: current manifest version string
- `module_root`: current shared module root, currently `vm/stdlib`
- `modules`: declared module entries

Each module entry currently declares:

- `name`: StackVM module name such as `stdlib.io`
- `ref`: canonical file-backed module loader ref such as `vm/stdlib/io`
- `file`: relative file path such as `vm/stdlib/io.vm`
- `summary`: short human-facing description
- `exports`: declared public exported helper names
- `dependencies`: declared stdlib module dependencies by package name, such as `stdlib.normalize`

The CLI now uses that manifest directly:

- `/stackvm list stdlib`
- `/stackvm stdlib list`
- `/stackvm stdlib show <module_name>`
- `/stackvm stdlib check`

StackVM target inspection now also reports stdlib package usage directly:

- `stdlib_modules_requested`: stdlib package modules requested through target `vm_modules`
- `stdlib_modules_resolved`: stdlib package modules that resolved to checked-in manifest-backed module files
- `stdlib_unresolved_refs`: any `stdlib.*` refs requested by a target that were not declared in the workspace stdlib manifest

When `stdlib_unresolved_refs` is non-empty, StackVM target inspection also emits a `stdlib-module-missing` warning so the missing manifest declaration is visible in `/stackvm inspect`, `/stackvm check`, and `/stackvm explain` without having to inspect the raw payload.

Reload-time workspace validation now also scans loaded VM flow definitions for undeclared `stdlib.*` refs and stores that summary on engine status. That means `/reload` and `/status` can surface workspace-wide stdlib drift even before a specific target is inspected.

That gives the checked-in stdlib a discoverable package surface even though StackVM still does not have a full package manager or lockfile model.

## Manifest Validation

The stdlib manifest is no longer only descriptive. The runtime now validates each declared stdlib module against the real module file by checking:

- the loader ref resolves successfully from the workspace root
- the resolved file matches the declared file path
- the actual declared StackVM module name matches the manifest `name`
- the actual exported helper set matches the manifest `exports`
- the actual imported stdlib module set matches the manifest `dependencies`

The canonical CLI entry point for that validation is:

```text
/stackvm stdlib check
```

Current validation output reports:

- package/version/module-root
- total module count
- warning count
- error count
- per-module validity plus any warnings or errors
- per-module declared and actual dependency sets through the returned payload

This is still a workspace-local package model. There is no registry or lockfile yet, but the manifest now serves as an enforceable declaration of the checked-in stdlib surface.

## Package Style

The stdlib uses the same explicit module surface as ordinary StackVM helper modules:

- `"name" module` declares the module namespace
- `"qualified.symbol" import` links exported helpers into a local module
- `"symbol" export` marks the public reusable surface

The current stdlib is intentionally small. It is meant to hold reusable helper words with stable semantics, not flow-specific orchestration.

## Current Modules

### `stdlib.io`

Defined in `vm/stdlib/io.vm`.

Exports:

- `read-file-once`
- `read-yaml-file-once`

Current behavior:

- `read-file-once` is a shared macro layer over the built-in `tool-once` pattern specialized for `core.read_file`
- `read-yaml-file-once` takes a file path expression, builds the `{path: ...}` request, parses it with `yaml>`, and then delegates through `read-file-once`

These helpers are intended for the recurring “read one workspace file, then keep the router focused on the later-turn logic” pattern.

Example:

```text
"payload.yaml"
[
  last-tool-result failure?
  [ "Could not load the payload." answer ]
  [
    last-tool-result "content" dict-get yaml>
    "payload" store-set
  ]
  if
]
stdlib.io.read-yaml-file-once
```

Checked-in consumers:

- `examples/stackvm_buttons_example/`
- `examples/stackvm_radio_example/`
- `examples/stackvm_checklist_handoff_example/`
- `examples/stackvm_normalize_ask_example/`
- `examples/stackvm_normalize_confirm_example/`
- `examples/stackvm_normalize_handoff_example/`
- `examples/stackvm_tool_normalize_example/`
- `examples/stackvm_config_router_example/`
- `examples/stackvm_nested_router_example/`
- `examples/stackvm_prompt_return_example/`
- `examples/stackvm_delegate_return_example/`
- `examples/stackvm_checklist_return_example/`
- `examples/stackvm_structured_return_routing_example/`
- `examples/stackvm_structured_return_finalize_example/`
- `examples/stackvm_nested_structured_return_example/`
- `examples/stackvm_nested_structured_return_routing_example/`
- `examples/stackvm_multistage_pipeline_example/`

### `stdlib.config`

Defined in `vm/stdlib/config.vm`.

Exports:

- `tool-content-yaml`
- `tool-content-schema-check`
- `tool-content-schema-apply`

Current behavior:

- `tool-content-yaml` parses `last-tool-result.content` as YAML
- `tool-content-schema-check` parses `last-tool-result.content` as YAML and runs `schema-check` against the schema already on the stack
- `tool-content-schema-apply` parses `last-tool-result.content` as YAML and runs `schema-apply` against the schema already on the stack

These helpers are intended for the recurring “tool loaded YAML config or payload, then validate/coerce it” pattern.

Example:

```text
"common" module
"stdlib.config.tool-content-schema-apply" import

[
  "{type: object, required: [enabled], properties: {enabled: {type: boolean}}}" yaml>
] "config-schema" define

[ config-schema tool-content-schema-apply ] "normalized-config" define
"normalized-config" export
```

Checked-in consumer:

- `examples/stackvm_config_router_example/`

### `stdlib.normalize`

Defined in `vm/stdlib/normalize.vm`.

Exports:

- `tool-content-yaml`
- `item-title`
- `normalize-item-titles`
- `store-normalized-source`
- `store-normalized-enabled`
- `store-normalized-summary`
- `format-selected-actions`

Current behavior:

- `tool-content-yaml` parses `last-tool-result.content` as YAML
- `item-title` extracts one item's `title` field and falls back to `"untitled"`
- `normalize-item-titles` reads `items`, maps them through `item-title`, stores `normalized.titles`, and stores a joined `normalized.title`
- `store-normalized-source` reads `meta.source` with fallback `"unknown"` and stores `normalized.source`
- `store-normalized-enabled` reads `items.0.enabled`, coerces it through `bool>`, falls back to `false`, and stores `normalized.enabled`
- `store-normalized-summary` stores `normalized.summary` from `normalized.title` plus `normalized.source`
- `format-selected-actions` joins a selected action list and stores `normalized.selected_actions_text`

These helpers are intended for the recurring “tool-loaded payload, normalize item titles and summary text, then prompt or route” pattern.

Example:

```text
"common" module
"stdlib.normalize.tool-content-yaml" "payload-data" import
"stdlib.normalize.normalize-item-titles" import
"stdlib.normalize.store-normalized-source" import
"stdlib.normalize.store-normalized-summary" import

"payload-data" export
"normalize-item-titles" export
"store-normalized-source" export
"store-normalized-summary" export
```

Checked-in consumers:

- `examples/stackvm_buttons_example/`
- `examples/stackvm_checklist_handoff_example/`
- `examples/stackvm_parallel_tool_map_example/`
- `examples/stackvm_reduce_tool_example/`
- `examples/stackvm_reduce_numeric_example/`
- `examples/stackvm_normalize_ask_example/`
- `examples/stackvm_normalize_confirm_example/`
- `examples/stackvm_normalize_handoff_example/`
- `examples/stackvm_threshold_router_example/`
- `examples/stackvm_tool_normalize_example/`
- `examples/stackvm_radio_example/`
- `examples/stackvm_prompt_return_example/`
- `examples/stackvm_delegate_return_example/`
- `examples/stackvm_checklist_return_example/`
- `examples/stackvm_structured_return_routing_example/`
- `examples/stackvm_structured_return_finalize_example/`
- `examples/stackvm_nested_structured_return_example/`
- `examples/stackvm_nested_structured_return_routing_example/`
- `examples/stackvm_multistage_pipeline_example/`

### `stdlib.prompt`

Defined in `vm/stdlib/prompt.vm`.

Exports:

- `buttons-approve-delegate-deny`
- `buttons-approve-reject`
- `radio-delegate-approve-deny`
- `radio-approve-escalate-review`
- `radio-concise-detailed-blocked`
- `radio-concise-blocked`
- `radio-review-first-delegate-now`
- `checklist-approve-delegate-review`
- `checklist-delegate-review-approve`
- `checklist-git-search-context`

Current behavior:

- each exported word pushes a prebuilt structured interaction request dictionary
- the current module surface covers the repeated checked-in buttons, radio, and checklist option sets used across interaction and delegate-return examples
- flows still customize the final prompt text locally, typically by setting `prompt` from `normalized.summary`

These helpers are intended for the recurring “shared normalization plus a stable structured interaction shape” pattern, where the option set is reused across more than one example and the flow-specific prompt text still belongs in the local script.

Example:

```text
"stdlib.prompt.buttons-approve-reject" import

[
  buttons-approve-reject
  dup "prompt" "Choose delegate action for " "normalized.summary" shared@ concat dict-set
  prompt-interaction
] "decide" define
```

Checked-in consumers:

- `examples/stackvm_buttons_example/`
- `examples/stackvm_radio_example/`
- `examples/stackvm_checklist_handoff_example/`
- `examples/stackvm_prompt_return_example/`
- `examples/stackvm_delegate_return_example/`
- `examples/stackvm_checklist_return_example/`
- `examples/stackvm_structured_return_finalize_example/`
- `examples/stackvm_structured_return_routing_example/`
- `examples/stackvm_nested_structured_return_example/`
- `examples/stackvm_nested_structured_return_routing_example/`
- `examples/stackvm_multistage_pipeline_example/`

### `stdlib.returns`

Defined in `vm/stdlib/returns.vm`.

Exports:

- `delegate-answer`
- `delegate-answer-yaml?`

Current behavior:

- `delegate-answer` reads `last_delegated_result.answer`
- `delegate-answer-yaml?` reads `last_delegated_result.answer`, returns `none` when the answer is missing, and otherwise parses the answer as YAML

These helpers are intended for caller-side flows that resume after `return_to_caller` handoff and need to inspect or parse the delegate's returned answer without repeating the same shared-store access logic.

Example:

```text
"common" module
"stdlib.returns.delegate-answer-yaml?" "stdlib-delegate-answer-yaml" import

[ stdlib-delegate-answer-yaml ] "delegate-answer-yaml?" define
"delegate-answer-yaml?" export
```

Checked-in consumers:

- `examples/stackvm_structured_return_routing_example/`
- `examples/stackvm_structured_return_finalize_example/`
- `examples/stackvm_nested_structured_return_example/`
- `examples/stackvm_nested_structured_return_routing_example/`

## Current Scope

The stdlib is still early-stage.

What is checked in today:

- a shared package location under workspace-root `vm/stdlib/`
- explicit-module authoring with exports/imports
- reusable io, config, normalization, prompt-construction, and return-parsing modules
- checked-in example usage across config-routing, prompt/interaction, delegate-return, structured-return, and multistage pipeline examples

What is not implemented yet:

- versioned package metadata
- dependency manifests beyond `vm_modules`
- a package manager or lockfile
- a large multi-module standard library

For now, treat `vm/stdlib/` as the canonical place for stable reusable StackVM helper modules that are broader than one flow namespace.
