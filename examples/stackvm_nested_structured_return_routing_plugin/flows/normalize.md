---
name: normalize
description: Normalize all tool-derived item titles, delegate a nested route choice, and route from the returned nested decision
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
---

Read a YAML payload through `core.read_file`, normalize all payload item titles, hand off to a VM delegate for a nested structured route choice, then parse the returned YAML and route to a final delegate.
