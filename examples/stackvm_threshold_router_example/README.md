# StackVM Threshold Router Example

This example shows a StackVM flow that reads a YAML payload through `core.read_file`, aggregates numeric item scores with `parallel-map` and `reduce`, and routes to a downstream delegate with the built-in `handoff-rules` macro based on the aggregate total.

Layout:

- `flows/*.md`: registers the StackVM router flow and the downstream delegates
- `flows/router.md`: StackVM-backed aggregate-and-route flow that loads the shared workspace stdlib normalization module plus the local VM modules explicitly
- `flows/low_route.py`: PocketFlow delegate for totals below the review threshold
- `flows/review_route.py`: PocketFlow delegate for totals in the review band
- `flows/high_route.py`: PocketFlow delegate for totals in the high band
- `vm/common.vm`: local facade that re-exports `stdlib.normalize.tool-content-yaml` as `payload-data`
- `vm/router.vm`: score normalization, aggregation, and threshold routing script using qualified `common.*` helper calls

The example demonstrates:

- tool-first orchestration with the built-in `tool-once` macro
- shared YAML parsing from a tool result through `stdlib.normalize.tool-content-yaml`
- pure data fan-out with `parallel-map` to normalize numeric item scores
- pure data fan-in with `reduce` to calculate the aggregate total
- declarative threshold routing with `handoff-rules`
- VM-to-PocketFlow handoff after the aggregate result is written into shared state
