# StackVM Parallel Tool Map Example

This example shows a StackVM flow that reads a YAML payload through `core.read_file`, extracts a list from the tool result, maps over that list with `parallel-map`, and answers from the collected result list.

Layout:

- `flows/*.md`: registers the StackVM flow
- `flows/map.md`: StackVM-backed tool-first mapping flow with `vm_module_prefixes` assigning the `common` helper prefix
- `vm/common.vm`: shared helper module for parsing the tool result into payload data, loaded as `common.*`
- `vm/router.vm`: tool-result loading and `parallel-map` script using qualified `common.*` helper calls

The example demonstrates:

- tool-first orchestration with the built-in `tool-once` macro
- YAML parsing from a tool result with `yaml>`
- safe list extraction with `dict-get?`
- pure data fan-out with `parallel-map` after the tool result is normalized into an in-memory list
- replay of a user-defined helper word inside child VMs spawned by `parallel-map`

This example keeps the `parallel-map` quotation pure after the tool result is loaded. The child quotation only transforms item data and does not perform runtime transitions.
