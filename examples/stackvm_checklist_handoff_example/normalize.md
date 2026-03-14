---
name: normalize
description: Normalize all tool-derived item titles, collect checklist actions, and hand off based on the selected list
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - stdlib.io
  - stdlib.normalize
  - vm/common
  - vm/router
---

Read a YAML payload through `stdlib.io.read-yaml-file-once`, normalize all payload item titles into shared state, collect checklist actions, and route to a downstream delegate based on the selected list.
