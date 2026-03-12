---
description: Architecture and planning specialist.
execution_mode: vm
vm_entry: start
llm_profile: gemini_default
tools:
  - read_file
  - list_files
  - search_code
  - core.glob_files
handoff_agents:
  - coder.coder
  - asker.ask
prompt_files:
  - architect.system.prompt.md
---

```vm
[
  "_llm_router" shared@ none?
  [ "continue" transition ]
  [ "llm_delegate" transition ]
  if
] "start" define
```
