# StackVM Nested Router Example

This example shows a StackVM flow that reads nested YAML config, normalizes it through `schema-apply`, routes with `match`, and records a nested audit field before handing off.

Layout:

- `flows` (*.md): registers the VM router plus the delegate and fallback flows
- `router.md`: StackVM-backed routing flow that loads the shared workspace stdlib io and config modules plus the local router modules explicitly
- `vm/common.vm`: declared helper module that defines the nested schema and applies `stdlib.config.tool-content-schema-apply` under `common.*`
- `vm/router.vm`: orchestration script using `match`, `list-get?`, `set-in?`, and qualified `common.*` helper calls over normalized nested config data
- `delegate.py`: PocketFlow delegate used when the nested config selects the primary route
- `fallback.py`: PocketFlow delegate used when nested routing is disabled or missing

The example demonstrates:

- loading shared file-read macros from workspace-root `stdlib.io`
- reading workspace config through the shared `stdlib.io.read-yaml-file-once` macro
- loading shared schema-application helpers from workspace-root `stdlib.config`
- schema-aware coercion and nested defaults with `schema-apply`
- structured routing with `match`
- safe list target selection with `list-get?`
- safe nested mutation with `set-in?`
- fallback on invalid nested config shapes that fail schema validation
- handoff based on nested config data with fallback on missing targets
