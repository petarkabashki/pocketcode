---
name: confirm_delegate
description: Collect a second structured decision through a radio prompt and return it to the caller
vm_entry: decide
vm_modules:
  - vm/delegate
---

Collect a second structured decision through `prompt-interaction` and return it to the caller via the handoff stack.