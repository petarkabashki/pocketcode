---
name: normalize
description: Normalize all payload item titles from YAML read through a tool before answering
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
vm_module_prefixes:
  vm/common: common
---

Read a YAML payload via a tool through the built-in `tool-once` macro, normalize all payload item titles plus selected fields into shared state, and answer from the normalized view.
