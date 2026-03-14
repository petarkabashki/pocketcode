# StackVM Reduce Tool Example

This example shows a StackVM flow that reads a YAML payload through `core.read_file`, extracts a list from the tool result, and folds the list into a single summary string with `reduce`.

Layout:

- `flows/*.md`: registers the StackVM flow
- `flows/summarize.md`: StackVM-backed tool-first reduction flow with `vm_module_prefixes` assigning the `common` helper prefix
- `vm/common.vm`: shared helper module for parsing the tool result into payload data, loaded as `common.*`
- `vm/router.vm`: tool-result loading plus `parallel-map` and `reduce` pipeline using qualified `common.*` helper calls

The example demonstrates:

- tool-first orchestration with the built-in `tool-once` macro
- YAML parsing from a tool result with `yaml>`
- safe list extraction with `dict-get?`
- pure data fan-out with `parallel-map` after the tool result is normalized into an in-memory list
- pure data fan-in with `reduce` to build one final summary string

This example keeps both child quotations pure after the tool result is loaded, so the collection pipeline stays within the combinator contract.
