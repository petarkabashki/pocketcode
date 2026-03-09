---
name: confirm_delegate
description: Collect a structured decision and return it as a YAML mapping string to the caller
vm_entry: decide
vm_modules:
  - vm/delegate
---

Collect a structured decision through `prompt-interaction` and return it to the caller as a YAML mapping string.
