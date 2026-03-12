---
name: normalize
description: Normalize all payload item titles from tool-derived YAML, delegate a structured decision, and finalize in the caller
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
---

Read a YAML payload through `core.read_file` with `tool-once`, normalize all payload item titles plus selected fields, hand off to a VM delegate for a structured decision, then parse the delegate's YAML answer and finalize in the caller with `finalize-from`.
