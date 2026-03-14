# StackVM Nested Router Example

This example shows a StackVM flow that reads nested YAML config, traverses mixed dict/list structures defensively, and records a nested audit field before handing off.

Layout:

- `flows/*.md`: registers the VM router plus the delegate and fallback flows
- `flows/router.md`: StackVM-backed routing flow with `vm_module_prefixes` assigning the `common` helper prefix
- `vm/common.vm`: shared helper module for parsing the tool result into config data, loaded as `common.*`
- `vm/router.vm`: orchestration script using `get-in?`, `list-get?`, `set-in?`, and qualified `common.*` helper calls
- `flows/delegate.py`: PocketFlow delegate used when the nested config selects the primary route
- `flows/fallback.py`: PocketFlow delegate used when nested routing is disabled or missing

The example demonstrates:

- reading workspace config via the real `core.read_file` `{path: ...}` contract
- safe nested traversal over mixed dict/list YAML data with `get-in?`
- safe list target selection with `list-get?`
- safe nested mutation with `set-in?`
- handoff based on nested config data with fallback on missing targets
