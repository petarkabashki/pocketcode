---
name: confirm_delegate
description: Collect a structured delegate choice and return a final answer to the caller
vm_entry: decide
vm_modules:
  - vm/delegate
---

Collect a structured decision through `prompt-interaction` and return the delegate answer directly to the caller through the handoff stack.
