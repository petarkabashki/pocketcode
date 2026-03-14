# StackVM Reduce Tool Example

This example shows a StackVM flow that reads a YAML payload through `core.read_file`, extracts a list from the tool result, and folds the list into a single summary string with `reduce`.

Layout:

- `flows/*.md`: registers the StackVM flow
- `flows/summarize.md`: StackVM-backed tool-first reduction flow that loads the shared workspace stdlib normalization module plus the local VM modules explicitly
- `vm/common.vm`: local facade that re-exports `stdlib.normalize.tool-content-yaml` as `payload-data`
- `vm/router.vm`: tool-result loading plus `parallel-map` and `reduce` pipeline using qualified `common.*` helper calls

The example demonstrates:

- tool-first orchestration with the built-in `tool-once` macro
- shared YAML parsing from a tool result through `stdlib.normalize.tool-content-yaml`
- safe list extraction with `dict-get?`
- pure data fan-out with `parallel-map` after the tool result is normalized into an in-memory list
- pure data fan-in with `reduce` to build one final summary string

This example keeps both child quotations pure after the tool result is loaded, so the collection pipeline stays within the combinator contract.
