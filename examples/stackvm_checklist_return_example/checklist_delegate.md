---
name: checklist_delegate
description: Collect checklist selections through prompt-interaction and return a final answer to the caller
vm_entry: decide
vm_modules:
  - vm/delegate
---

Collect multiple selections through `prompt-interaction` and return the delegate answer to the caller via the handoff stack.