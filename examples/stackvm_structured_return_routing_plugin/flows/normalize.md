---
name: normalize
description: Normalize all tool-derived item titles, delegate a route choice, and route from the returned structured decision
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
---

Read a YAML payload through `core.read_file`, normalize all payload item titles, hand off to a VM delegate for a route choice, then parse the delegate's YAML answer and route to a final delegate.
