---
name: test_ask
execution_mode: vm
vm_entry: main
---
```vm
[
  "Prompt one:" ask-user 
  "User said: " swap concat answer
] "main" define
```
