# StackVM Normalize Handoff Example

This example shows a StackVM flow that reads YAML through a tool, normalizes all payload item titles plus selected fields into shared state, and then hands off to different PocketFlow delegates based on the normalized result.

Layout:

- `flows/*.md`: registers the StackVM normalization router plus enabled and disabled delegates
- `flows/normalize.md`: StackVM-backed normalization-and-handoff flow with `vm_module_prefixes` assigning the `common` helper prefix
- `vm/common.vm`: shared helper module for parsing and normalizing the tool-derived payload, loaded as `common.*`
- `vm/router.vm`: normalization script using `tool-once`, `parallel-map`, `switch`, and qualified `common.*` helper calls before handoff
- `flows/enabled_delegate.py`: PocketFlow delegate for enabled normalized payloads
- `flows/disabled_delegate.py`: PocketFlow delegate for disabled normalized payloads

The example demonstrates:

- tool-first orchestration with the built-in `tool-once` macro
- normalization of tool-derived YAML into shared state
- fan-out normalization of all payload item titles with `parallel-map`
- exact-match enabled or disabled routing with `switch` after normalization
- handoff decisions based on normalized shared-store values rather than raw tool payload structure
- delegate flows that consume the normalized shared-state contract instead of re-parsing the payload
