---
name: tool_loop
---

```vm
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