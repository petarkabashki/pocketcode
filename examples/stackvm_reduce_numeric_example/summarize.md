---
name: summarize
description: Load YAML via a tool, normalize numeric item values, and fold them into a total with reduce
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
vm_module_prefixes:
  vm/common: common
---

Load a YAML payload via `core.read_file`, normalize its numeric item values into an in-memory list, and fold those values into one final total.
