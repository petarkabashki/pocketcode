---
description: >
  General-purpose ReAct agent. Reasons, calls core tools, and observes
  results in a Reason -> Act -> Observe loop until a final answer is reached.
module: core.react_agent.py
entry_fn: create_flow
llm_profile: gemini_default
default_agent:
  name: core.react
  flow: core.react
  description: Built-in composite agent for the default ReAct flow.
tools:
  - read_file
  - write_to_file
  - list_files
  - create_directory
  - glob_files
  - select_filesystem_entry
  - extract_text
  - stage_text_replace
  - apply_staged_edit
  - cancel_staged_edit
  - search_code
  - execute_command
  - ask_user_input
  - ask_user_buttons
  - ask_user_radio_group
  - ask_user_checklist
  - confirm_user_input
  - workspace_git.git_status
  - workspace_git.git_diff
  - workspace_git.git_add
  - workspace_git.git_commit
  - workspace_git.git_pull
  - workspace_git.git_push
  - workspace_context.read_context_elephant_store_file
  - workspace_context.write_context_elephant_store_file
  - workspace_context.append_to_context_elephant_store_file
  - workspace_context.get_context_elephant_store_summary
  - workspace_context.check_context_elephant_store_status
---
