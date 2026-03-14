---
name: normalize
description: Normalize all payload item titles from tool-derived YAML, hand off to a prompted delegate, and finalize from the delegate return payload
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - stdlib.io
  - stdlib.normalize
  - vm/common
  - vm/router
---

Read a YAML payload through `stdlib.io.read-yaml-file-once`, normalize all payload item titles plus selected fields into shared state, hand off to a prompted delegate with `return_to_caller`, and finalize from `last_delegated_result` with `finalize-from` when the delegate returns.
