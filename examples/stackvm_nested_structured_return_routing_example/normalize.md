---
name: normalize
description: Normalize all tool-derived item titles, delegate a nested route choice, and route from the returned nested decision
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - stdlib.io
  - stdlib.normalize
  - vm/common
  - vm/router
---

Read a YAML payload, apply the standard checked-in normalization contract, hand off to a VM delegate for a nested structured route choice expressed through `define-choice-route-family`, then resume through the same contract with nested field specs and defaults.
