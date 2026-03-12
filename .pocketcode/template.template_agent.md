---
name: template-agent
description: A minimal programmatic workspace flow wired through Markdown-first discovery.
execution_mode: vm
vm_entry: decide
tools:
  - hello_world
default_agent:
  name: template.template-agent
  flow: template.template-agent
  description: Minimal programmatic workspace flow.
---

```vm
[
  last-tool-result none?
  [
    "_tool_runtime" shared@ none?
    [ "Hello from Programmatic Flow!" answer ]
    [ "template.hello_world" {name: "PocketFlow User"} tool-request ]
    if
  ]
  [
    last-tool-result "message" dict-get? dup none?
    [ drop "Hello from Programmatic Flow!" ]
    [ ]
    if
    answer
  ]
  if
] "decide" define
```
