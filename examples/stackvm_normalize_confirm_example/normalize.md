---
name: normalize
description: Normalize all payload item titles from tool-derived YAML, prompt for confirmation, and continue to a final answer
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
---

Read a YAML payload through `core.read_file`, normalize all payload item titles plus selected fields into shared state, ask for confirmation through the bridged interaction channel, and continue to a final answer.