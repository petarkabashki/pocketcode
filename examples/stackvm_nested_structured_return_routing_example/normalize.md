---
name: normalize
description: Normalize all tool-derived item titles, delegate a nested route choice, and route from the returned nested decision
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
vm_module_prefixes:
  vm/common: common
---

Read a YAML payload through `core.read_file` with `tool-once`, normalize all payload item titles, hand off to a VM delegate for a nested structured route choice, then parse the returned YAML and route to a final delegate.
