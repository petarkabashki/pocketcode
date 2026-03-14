---
name: normalize
description: Normalize all tool-derived item titles, delegate a route choice, and route from the returned structured decision
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - stdlib.io
  - stdlib.normalize
  - vm/common
  - vm/router
---

Read a YAML payload, apply the standard checked-in normalization contract, hand off to a VM delegate for a route choice expressed through `define-choice-route-family`, then resume through the same contract so the caller routes from declarative returned-field specs instead of manual YAML projection code.
