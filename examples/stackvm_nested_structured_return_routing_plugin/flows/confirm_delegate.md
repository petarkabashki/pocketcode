---
name: confirm_delegate
description: Collect a route choice and return it as a nested YAML decision string to the caller
vm_entry: decide
vm_modules:
  - vm/delegate
---

Collect a structured route choice through `prompt-interaction` and return it to the caller as a nested YAML mapping string.
