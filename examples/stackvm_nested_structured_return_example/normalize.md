---
name: normalize
description: Normalize all payload item titles from tool-derived YAML, delegate a nested structured decision, and finalize in the caller
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
---

Read a YAML payload through `core.read_file` with `tool-once`, normalize all payload item titles plus selected fields, hand off to a VM delegate for a nested structured decision, then parse the returned YAML and finalize from nested fields in the caller with `finalize-from`.
