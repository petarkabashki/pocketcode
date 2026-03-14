---
name: router
description: Nested-data StackVM router
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - stdlib.io
  - stdlib.config
  - vm/common
  - vm/router
---

Read nested YAML config data through `stdlib.io.read-yaml-file-once`, traverse it defensively, and hand off to the selected route.
