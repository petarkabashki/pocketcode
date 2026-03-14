---
name: normalize
description: Normalize tool-derived payload data, delegate with return_to_caller, and pass the delegate answer through
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - stdlib.io
  - stdlib.normalize
  - vm/common
  - vm/router
---

Read a YAML payload through `stdlib.io.read-yaml-file-once`, normalize all payload item titles into shared state, hand off to a prompted delegate with the built-in `return-delegate` macro, and pass the delegate answer directly back through the caller.
