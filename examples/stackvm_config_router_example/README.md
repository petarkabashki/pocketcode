# StackVM Config Router Example

This example shows a StackVM flow that reads YAML from the workspace, coerces config values, selects a route from a list, and hands off to a PocketFlow delegate.

Layout:

- `flows/*.md`: registers the VM router plus the delegate and fallback flows
- `flows/router.md`: StackVM-backed routing flow with `vm_module_prefixes` assigning the `common` helper prefix
- `vm/common.vm`: shared helper module for parsing the tool result into config data, loaded as `common.*`
- `vm/router.vm`: orchestration script using `bool>`, `int>`, `list-get`, and qualified `common.*` helper calls
- `flows/delegate.py`: PocketFlow delegate used when the config selects the primary route
- `flows/fallback.py`: PocketFlow delegate used when the config disables routing or the tool request fails

The example demonstrates:

- reading workspace config via the real `core.read_file` `{path: ...}` contract
- YAML parsing with `yaml>`
- value coercion with `bool>` and `int>`
- defensive route selection with `dict-get?` and `list-get?`
- handoff based on config data instead of hardcoded transitions
- fallback on both disabled config and missing config file paths
- fallback when the configured route index does not resolve to a target
