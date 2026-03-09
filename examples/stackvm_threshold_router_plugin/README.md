# StackVM Threshold Router Example

This example shows a StackVM flow that reads a YAML payload through `core.read_file`, aggregates numeric item scores with `parallel-map` and `reduce`, and routes to a downstream delegate with `cond` based on the aggregate total.

Layout:

- `plugin.yaml`: registers the StackVM router flow and the downstream delegates
- `flows/router.md`: StackVM-backed aggregate-and-route flow
- `flows/low_route.py`: PocketFlow delegate for totals below the review threshold
- `flows/review_route.py`: PocketFlow delegate for totals in the review band
- `flows/high_route.py`: PocketFlow delegate for totals in the high band
- `vm/common.vm`: shared word for parsing the tool result into payload data
- `vm/router.vm`: score normalization, aggregation, and threshold routing script

The example demonstrates:

- tool-first orchestration with `tool-request`
- pure data fan-out with `parallel-map` to normalize numeric item scores
- pure data fan-in with `reduce` to calculate the aggregate total
- declarative threshold routing with `cond`
- VM-to-PocketFlow handoff after the aggregate result is written into shared state