---
name: review
flow: core.react
description: Self-contained review agent migrated from stackvm_example
llm_profile: fast
tools:
  - core.read_file
vm_entry: decide
vm_modules: []
---

Review the current request conservatively and prefer reading context before answering.

```vm
# From vm/common.vm
[ last-tool-result "content" dict-get ] "tool-content" define
[ request "request_text" store-set ] "capture-request" define

# From flows/review.md
[ request "request_text" store-set ] "bootstrap" define

# From vm/tool_loop.md
[ 
  bootstrap
  last-tool-result none?
  [
    "core.read_file"
    "{path: readme.md}" yaml>
    tool-request
  ]
  [
    tool-content
    dup none?
    [ drop "No readable content returned." answer ]
    [ answer ]
    if
  ]
  if
] "decide" define
```
