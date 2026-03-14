---
name: normalize
description: Normalize all tool-derived item titles, present structured button choices, and continue to a final answer
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
vm_module_prefixes:
  vm/common: common
---

Read a YAML payload through `core.read_file` with `tool-once`, normalize all payload item titles into shared state, present structured button choices through `prompt-route`, and continue to a final answer.
