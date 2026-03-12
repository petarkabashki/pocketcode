# StackVM Macro Authoring Example

This example shows a StackVM flow that keeps repeated YAML data in helper words and layers user-authored macros on top for the orchestration and final answer shape.

Layout:

- `flows/*.md`: registers the StackVM flow
- `flows/normalize.md`: StackVM-backed flow description and VM module wiring
- `vm/common.vm`: helper words for the YAML request payload and parsed message extraction
- `vm/router.vm`: user-authored macros plus the caller logic that uses them

The example demonstrates:

- using a helper word instead of repeating a YAML request literal
- defining custom macros with `defmacro` and `syntax-quote`
- using `unquote` to pass a request quotation and later-turn quotation into a custom wrapper macro
- using `unquote-splice` to inline a quotation body before `answer`
- layering custom macros on top of the built-in `tool-once` macro rather than replacing the runtime model

Conceptually:

- `read-file-once` expands to a `tool-once` call specialized for `core.read_file`
- `answer-from` expands to the supplied quotation body followed by `answer`

Use this example when the repeated part is partly runtime data and partly control-flow shape, so helper words alone would still leave noisy orchestration at the call site.
