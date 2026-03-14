---
name: confirm_delegate
description: Collect a second structured decision through a radio prompt and return it to the caller
vm_entry: decide
vm_modules:
  - stdlib.normalize
  - vm/common
  - vm/delegate
---

Collect a second structured decision through the delegate half of `define-choice-continue-answer-family` and return it to the caller via the handoff stack.
