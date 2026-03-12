# StackVM Review Example

This example shows a multi-file StackVM-backed flow packaged as a normal workspace namespace.

Layout:

- `flows/*.md`: registers the flow
- `flows/review.md`: declares the Markdown-backed flow and the VM entry point
- `vm/common.vm`: shared words for request capture and result access
- `vm/tool_loop.md`: a Markdown-authored VM module with the orchestration word definitions

The example is intentionally small. It demonstrates:

- `vm_entry`, `vm_modules`, and `vm_files`
- mixed `.vm` and `.md` VM source files
- slash-style module refs such as `vm/common` without requiring a file suffix
- request capture with `store-set`
- tool-first orchestration with `tool-request` against the real `core.read_file` `{path: ...}` contract
- follow-up answer generation from `last-tool-result`

See also `../stackvm_handoff_example/` for a VM flow that uses agent handoff instead of a tool loop.
