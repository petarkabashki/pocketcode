---
name: normalize
description: Normalize all payload item titles from tool-derived YAML, collect checklist actions, and finalize after a delegate returns a second decision
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
---

Read a YAML payload through `core.read_file`, normalize all payload item titles plus selected fields, collect checklist actions, hand off to a delegate for a second decision, and finalize back in the caller after the delegate returns.