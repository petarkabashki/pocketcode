---
name: tool_loop
---

```vm
[ request "request_text" store-set ] "bootstrap" define
[ last-tool-result "content" dict-get ] "common.tool-content" define

[ 
  bootstrap
  last-tool-result none?
  [
    "core.read_file"
    "{path: readme.md}" yaml>
    tool-request
  ]
  [
    common.tool-content
    dup none?
    [ drop "No readable content returned." answer ]
    [ answer ]
    if
  ]
  if
] "decide" define
```
