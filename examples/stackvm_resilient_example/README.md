# StackVM Resilient Example

This example shows a StackVM flow that requests a tool, checks the returned success contract, and hands off when the tool fails.

Layout:

- `flows/*.md`: registers the VM router plus the fallback delegate
- `flows/router.md`: StackVM-backed routing flow with `vm_module_prefixes` assigning the `common` helper prefix
- `vm/common.vm`: shared utility words for reading the tool payload, loaded as `common.*`
- `vm/router.vm`: orchestration script with failure branching, handoff, and qualified `common.*` helper calls where needed
- `flows/fallback.py`: PocketFlow delegate used on failure

The example demonstrates:

- `tool-request` followed by `last-tool-result`
- `success?` and `failure?`
- nested access with `get-in`
- the real `core.read_file` `{path: ...}` request shape
- handoff after a failed tool call
