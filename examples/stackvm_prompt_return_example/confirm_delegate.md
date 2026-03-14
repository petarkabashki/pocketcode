---
name: confirm_delegate
description: Prompt for a structured delegate decision and return a final answer to the caller
vm_entry: decide
vm_modules:
  - stdlib.normalize
  - vm/common
  - vm/delegate
---

Collect a structured decision through the paired answer workflow declared in `vm/common.vm` with `define-choice-answer-family` and return the delegate answer to the caller via the handoff stack.
