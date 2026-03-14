---
name: confirm_delegate
description: Collect a route choice and return it as a YAML decision string to the caller
vm_entry: decide
vm_modules:
  - stdlib.normalize
  - vm/common
  - vm/delegate
---

Collect a structured route choice through the delegate half of `define-choice-route-family`, declare the returned decision as path/value field specs, and serialize it to YAML at the answer boundary.
