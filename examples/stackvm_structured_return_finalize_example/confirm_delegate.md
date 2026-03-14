---
name: confirm_delegate
description: Collect a structured decision and return it as a YAML mapping string to the caller
vm_entry: decide
vm_modules:
  - stdlib.normalize
  - vm/common
  - vm/delegate
---

Collect a structured decision through the delegate half of `define-choice-finalize-family`, declare the returned decision as path/value field specs, and serialize it to YAML at the answer boundary.
