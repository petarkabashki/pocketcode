---
name: confirm_delegate
description: Collect a route choice and return it as a nested YAML decision string to the caller
vm_entry: decide
vm_modules:
  - stdlib.normalize
  - vm/common
  - vm/delegate
---

Collect a structured route choice through the delegate half of `define-choice-route-family`, declare nested returned decision data as path/value field specs on top of a shared base mapping, and serialize the result to YAML at the answer boundary.
