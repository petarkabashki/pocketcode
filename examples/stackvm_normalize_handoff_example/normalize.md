---
name: normalize
description: Normalize all payload item titles from tool-derived YAML and hand off based on the normalized shared state
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
---

Read a YAML payload through `core.read_file`, normalize all payload item titles plus selected fields into shared state, and hand off to the matching delegate.