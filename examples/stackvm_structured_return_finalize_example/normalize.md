---
name: normalize
description: Normalize all payload item titles from tool-derived YAML, delegate a structured decision, and finalize in the caller
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - stdlib.io
  - stdlib.normalize
  - vm/common
  - vm/router
---

Read a YAML payload, apply the standard checked-in normalization contract, hand off to a VM delegate for a structured decision expressed through `define-choice-finalize-family`, then resume through the same contract so the caller finalizes from declarative returned-field specs instead of manual YAML projection code.
