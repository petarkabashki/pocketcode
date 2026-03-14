---
name: normalize
description: Normalize all tool-derived item titles, collect checklist actions, and hand off based on the selected list
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
vm_module_prefixes:
  vm/common: common
---

Read a YAML payload through `core.read_file`, normalize all payload item titles into shared state, collect checklist actions, and route to a downstream delegate based on the selected list.
