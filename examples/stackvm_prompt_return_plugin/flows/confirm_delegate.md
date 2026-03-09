---
name: confirm_delegate
description: Prompt for a structured delegate decision and return a final answer to the caller
vm_entry: decide
vm_modules:
  - vm/delegate
---

Collect a structured decision through `prompt-interaction` and return the delegate answer to the caller via the handoff stack.