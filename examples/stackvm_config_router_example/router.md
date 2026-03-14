---
name: router
description: Config-driven StackVM router
tools:
  - core.read_file
vm_entry: router.decide
vm_modules:
  - stdlib.io
  - stdlib.config
  - vm/common
  - vm/router
---

Read a workspace YAML config through `stdlib.io.read-yaml-file-once`, coerce its values, and route to the selected delegate.
