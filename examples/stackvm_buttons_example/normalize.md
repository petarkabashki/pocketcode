---
name: normalize
description: Normalize all tool-derived item titles, present structured button choices, and continue to a final answer
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - stdlib.io
  - stdlib.normalize
  - vm/common
  - vm/router
---

Read a YAML payload, apply the standard checked-in normalization contract through `normalize-loaded-payload`, then present structured button choices through `define-choice-continue-spec` plus `use-workflow-spec` so the file-load, normalization, normalized-summary prompt, and `continue` plus `exact` routing policy are declared from one authored surface.
