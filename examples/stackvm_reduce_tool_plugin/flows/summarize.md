---
name: summarize
description: Load YAML via a tool, map over items, and fold them into a single summary with reduce
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
---

Load a YAML payload via `core.read_file`, normalize its items into an in-memory list, and fold the mapped item labels into one final summary.