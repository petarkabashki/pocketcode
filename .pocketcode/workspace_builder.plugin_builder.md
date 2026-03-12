---
description: Create and edit workspace namespace resources and workspace-level assets.
execution_mode: vm
vm_entry: start
llm_profile: gemini_default
tools:
  - core.read_file
  - core.write_to_file
  - core.list_files
  - core.create_directory
  - core.glob_files
  - core.select_filesystem_entry
  - core.extract_text
  - core.stage_text_replace
  - core.apply_staged_edit
  - core.cancel_staged_edit
  - core.search_code
  - core.execute_command
  - core.ask_user_input
  - workspace_git.git_status
  - workspace_git.git_diff
prompt_files:
  - workspace_builder.system.prompt.md
---

```vm
[
  "_llm_router" shared@ none?
  [ "continue" transition ]
  [ "llm_delegate" transition ]
  if
] "start" define
```
