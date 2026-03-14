---
name: review
description: Example StackVM-backed review flow
llm_profile: fast
tools:
  - core.read_file
vm_entry: decide
vm_modules:
  - vm/common
vm_module_prefixes:
  vm/common: common
vm_files:
  - vm/tool_loop.md
---

Review the current request conservatively and prefer reading context before answering.

```vm
[ request "request_text" store-set ] "bootstrap" define
```
