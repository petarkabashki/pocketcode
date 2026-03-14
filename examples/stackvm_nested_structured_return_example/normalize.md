---
name: normalize
description: Normalize all payload item titles from tool-derived YAML, delegate a nested structured decision, and finalize in the caller
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - stdlib.io
  - stdlib.normalize
  - vm/common
  - vm/router
---

Read a YAML payload, apply the standard checked-in normalization contract, hand off to a VM delegate for a nested structured decision expressed through `define-choice-finalize-family`, then resume through the same contract with nested field specs and defaults.
