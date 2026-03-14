---
name: router
description: Aggregate numeric item scores and route to a downstream delegate based on the total
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
vm_module_prefixes:
  vm/common: common
---

Load a YAML payload via `core.read_file`, aggregate numeric item scores, and hand off according to threshold bands derived from the total.
