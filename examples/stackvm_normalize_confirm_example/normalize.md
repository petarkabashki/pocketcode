---
name: normalize
description: Normalize all payload item titles from tool-derived YAML, prompt for confirmation, and continue to a final answer
tools:
  - core.read_file
vm_modules:
  - stdlib.io
  - stdlib.normalize
  - vm/common
  - vm/router
---

Read a YAML payload through `stdlib.io.read-yaml-file-once`, normalize all payload item titles plus selected fields into shared state, ask for confirmation through the bridged interaction channel, and continue to a final answer.

```vm
[ router.decide ] "main" define
```
