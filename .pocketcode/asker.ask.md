---
description: Repository Q&A and clarification specialist.
execution_mode: vm
vm_entry: start
llm_profile: gemini_fast
tools:
  - ask_user_input
  - core.read_file
  - core.list_files
  - core.glob_files
  - core.search_code
handoff_agents:
  - coder.coder
  - architect.architect
prompt_files:
  - asker.system.prompt.md
---

```vm
[
  "_llm_router" shared@ none?
  [ "continue" transition ]
  [ "llm_delegate" transition ]
  if
] "start" define
```
