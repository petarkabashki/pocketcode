# StackVM Reduce Numeric Example

This example shows a StackVM flow that reads a YAML payload through `core.read_file`, normalizes numeric item values into an in-memory list, and folds that list into a numeric total with `reduce`.

Layout:

- `flows/*.md`: registers the StackVM flow
- `flows/summarize.md`: StackVM-backed numeric aggregation flow that loads the shared workspace stdlib normalization module plus the local VM modules explicitly
- `vm/common.vm`: local facade that re-exports `stdlib.normalize.tool-content-yaml` as `payload-data`
- `vm/router.vm`: tool-result loading plus numeric normalization and `reduce` pipeline using qualified `common.*` helper calls

The example demonstrates:

- tool-first orchestration with `tool-request`
- shared YAML parsing from a tool result through `stdlib.normalize.tool-content-yaml`
- safe numeric normalization with `dict-get?`, `none?`, and `int>`
- pure data fan-out with `parallel-map` to extract numeric item values
- pure data fan-in with `reduce` to calculate a numeric total

This example keeps both child quotations pure after the tool result is loaded, so the collection pipeline stays within the combinator contract while demonstrating numeric aggregation instead of string formatting.
