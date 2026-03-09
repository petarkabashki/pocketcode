---
name: normalize
description: Normalize all tool-derived item titles, present a radio interaction, and continue to a final answer
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
---

Read a YAML payload through `core.read_file`, normalize all payload item titles into shared state, present a radio choice through the bridged interaction channel, and continue to a final answer.