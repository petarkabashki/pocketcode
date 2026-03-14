---
name: normalize
description: Normalize tool-derived payload data, delegate with return_to_caller, and pass the delegate answer through
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
vm_module_prefixes:
  vm/common: common
---

Read a YAML payload through `core.read_file` with `tool-once`, normalize all payload item titles into shared state, hand off to a prompted delegate with `return_to_caller`, and pass the delegate answer directly back through `delegate-return`.
