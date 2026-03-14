---
name: confirm_delegate
description: Collect a structured delegate choice and return a final answer to the caller
vm_entry: decide
vm_modules:
  - stdlib.normalize
  - vm/common
  - vm/delegate
---

Collect a structured decision through the delegate answer spec declared in `vm/common.vm` with `define-choice-answer-spec` and return the delegate answer directly to the caller through the handoff stack.
