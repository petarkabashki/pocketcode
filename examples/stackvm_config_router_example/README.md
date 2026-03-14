# StackVM Config Router Example

This example shows a StackVM flow that reads YAML from the workspace, normalizes it through `schema-apply`, routes with `match`, selects a route from a list, and hands off to a PocketFlow delegate.

Layout:

- `flows/*.md`: registers the VM router plus the delegate and fallback flows
- `flows/router.md`: StackVM-backed routing flow loading the shared workspace stdlib io and config modules plus explicit local helper/router modules
- `vm/common.vm`: local helper module declaring the config schema and importing the shared `stdlib.config.tool-content-schema-apply` helper
- `vm/router.vm`: orchestration script using `match`, `list-get?`, and explicit module imports over normalized config data
- `flows/delegate.py`: PocketFlow delegate used when the config selects the primary route
- `flows/fallback.py`: PocketFlow delegate used when the config disables routing or the tool request fails

The example demonstrates:

- loading a shared workspace-root StackVM stdlib module from `stdlib.io`
- loading a shared workspace-root StackVM stdlib module from `stdlib.config`
- reading workspace config through the shared `stdlib.io.read-yaml-file-once` macro
- YAML parsing with `yaml>`
- schema-aware coercion and defaults with `schema-apply`
- structured routing with `match`
- defensive route selection with `list-get?` after the config is normalized
- handoff based on config data instead of hardcoded transitions
- fallback on both disabled config and missing config file paths
- fallback on invalid config shapes that fail schema validation
- fallback when the configured route index does not resolve to a target
