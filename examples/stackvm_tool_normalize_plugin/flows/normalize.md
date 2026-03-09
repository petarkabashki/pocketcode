---
name: normalize
description: Normalize all payload item titles from YAML read through a tool before answering
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
---

Read a YAML payload via a tool, normalize all payload item titles plus selected fields into shared state, and answer from the normalized view.