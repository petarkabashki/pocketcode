# StackVM Reduce Example

This example shows a StackVM flow that maps over a fixed list with `parallel-map`, folds the mapped values with `reduce`, and answers from the final accumulator.

Layout:

- `flows/*.md`: registers the StackVM flow
- `flows/summarize.md`: StackVM-backed map-and-reduce flow
- `vm/router.vm`: helper words plus `parallel-map` and `reduce` pipeline

The example demonstrates:

- pure data fan-out with `parallel-map`
- pure data fan-in with `reduce`
- replay of user-defined helper words inside child VMs spawned by both combinators

This example intentionally keeps both quotations pure so the full pipeline stays within the collection-combinator contract.