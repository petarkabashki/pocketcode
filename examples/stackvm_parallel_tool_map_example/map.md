---
name: map
description: Load YAML via a tool, map over items with parallel-map, and answer from the mapped results
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
---

Load a YAML payload via `core.read_file`, fan out over the payload items with `parallel-map`, and format the collected results into a final answer.