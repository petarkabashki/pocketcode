---
name: router
description: StackVM flow that hands off on tool failure
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
---

Try a read first, then route to the fallback flow if the tool reports failure.