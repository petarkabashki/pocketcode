# StackVM Resilient Example

This example shows a StackVM flow that requests a tool, checks the returned success contract, and hands off when the tool fails.

Layout:

- `flows` (*.md): registers the VM router plus the fallback delegate
- `router.md`: StackVM-backed routing flow with explicit module loading
- `vm/common.vm`: declared helper module exporting shared tool-result helpers under `common.*`
- `vm/router.vm`: orchestration script with failure branching, handoff, and direct tool-result inspection
- `fallback.py`: PocketFlow delegate used on failure

The example demonstrates:

- `tool-request` followed by `last-tool-result`
- `success?` and `failure?`
- nested access with `get-in`
- the real `core.read_file` `{path: ...}` request shape
- handoff after a failed tool call
