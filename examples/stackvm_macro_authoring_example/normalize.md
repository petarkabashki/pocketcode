---
name: normalize
description: Read a YAML payload through a helper word plus user-authored macros and answer from expanded StackVM
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
  - vm/router
---

Read a YAML payload through a helper word and a user-authored macro, then answer from the parsed message through another user-authored macro.
