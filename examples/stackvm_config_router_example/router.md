---
name: router
description: Config-driven StackVM router
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
---

Read a workspace YAML config, coerce its values, and route to the selected delegate.