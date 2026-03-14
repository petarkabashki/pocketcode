---
name: confirm_delegate
description: Collect a structured decision and return it as a nested YAML mapping string to the caller
vm_entry: decide
vm_modules:
  - stdlib.normalize
  - vm/common
  - vm/delegate
---

Collect a structured decision through the delegate half of `define-choice-finalize-family`, declare nested returned decision data as path/value field specs on top of a shared base mapping, and serialize the result to YAML at the answer boundary.
