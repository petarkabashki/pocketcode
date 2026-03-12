---
description: Code implementation and editing specialist.
execution_mode: vm
vm_entry: start
llm_profile: gemini_default
tools:
  - write_to_file
  - create_directory
  - git_diff
  - core.read_file
  - core.list_files
  - core.glob_files
  - core.search_code
  - core.execute_command
  - workspace_git.git_status
  - workspace_git.git_add
  - workspace_git.git_commit
  - workspace_git.git_pull
  - workspace_git.git_push
handoff_agents:
  - architect.architect
  - asker.ask
prompt_files:
  - coder.system.prompt.md
---

```vm
[
  "_llm_router" shared@ none?
  [ "continue" transition ]
  [ "llm_delegate" transition ]
  if
] "start" define
```
