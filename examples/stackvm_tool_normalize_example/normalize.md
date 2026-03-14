---
name: normalize
description: Normalize all payload item titles from YAML read through a tool before answering
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - stdlib.io
  - stdlib.normalize
  - vm/common
  - vm/router
---

Read a YAML payload through `stdlib.io.read-yaml-file-once`, normalize all payload item titles plus selected fields into shared state, and answer from the normalized view.
