---
name: router
description: Nested-data StackVM router
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
vm_module_prefixes:
  vm/common: common
---

Read nested YAML config data, traverse it defensively, and hand off to the selected route.
