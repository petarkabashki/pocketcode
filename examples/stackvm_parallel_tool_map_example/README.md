# StackVM Parallel Tool Map Example

This example shows a StackVM flow that reads a YAML payload through `core.read_file`, extracts a list from the tool result, maps over that list with `parallel-map`, and answers from the collected result list.

Layout:

- `flows/*.md`: registers the StackVM flow
- `flows/map.md`: StackVM-backed tool-first mapping flow that loads the shared workspace stdlib normalization module plus the local VM modules explicitly
- `vm/common.vm`: local facade that re-exports `stdlib.normalize.tool-content-yaml` as `payload-data`
- `vm/router.vm`: tool-result loading and `parallel-map` script using qualified `common.*` helper calls

The example demonstrates:

- tool-first orchestration with the built-in `tool-once` macro
- shared YAML parsing from a tool result through `stdlib.normalize.tool-content-yaml`
- safe list extraction with `dict-get?`
- pure data fan-out with `parallel-map` after the tool result is normalized into an in-memory list
- replay of a user-defined helper word inside child VMs spawned by `parallel-map`

This example keeps the `parallel-map` quotation pure after the tool result is loaded. The child quotation only transforms item data and does not perform runtime transitions.
