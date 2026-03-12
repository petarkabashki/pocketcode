---
description: Orchestrates specialist sub-agents to handle complex multi-step tasks.
execution_mode: vm
vm_entry: route
llm_profile: default
tools:
  - execute_command
handoff_agents:
  - coder.coder
  - architect.architect
  - asker.ask
prompt_files:
  - micromanager.system.prompt.md
---

```vm
[
  request str> "req" store-set
  "req" store-get "" =
  [
    "messages" shared@ dup none?
    [ drop "" ]
    [ dup len 1 - list-get? dup dict? [ "content" dict-get? ] [ str> ] if ]
    if "req" store-set
  ]
  [ ]
  if

  "req" store-get str> "lower_req" store-set

  [
    [ "lower_req" store-get "code" contains?
      "lower_req" store-get "implement" contains? or
      "lower_req" store-get "write" contains? or
      "lower_req" store-get "fix" contains? or
      "lower_req" store-get "debug" contains? or
      "lower_req" store-get "refactor" contains? or
    ] [ "coder::coder" ]
    [ "lower_req" store-get "architect" contains?
      "lower_req" store-get "design" contains? or
      "lower_req" store-get "plan" contains? or
      "lower_req" store-get "structure" contains? or
      "lower_req" store-get "scaffold" contains? or
    ] [ "architect::architect" ]
    [ "lower_req" store-get "ask" contains?
      "lower_req" store-get "question" contains? or
      "lower_req" store-get "explain" contains? or
      "lower_req" store-get "help" contains? or
      "lower_req" store-get "what" contains? or
      "lower_req" store-get "how" contains? or
      "lower_req" store-get "why" contains? or
    ] [ "asker::ask" ]
    [ True ] [ "coder::coder" ]
  ] cond
  handoff
] "route" define
```
