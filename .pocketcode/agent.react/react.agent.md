---
name: react
description: A ReAct agent running natively in StackVM.
execution_mode: vm
flow: agents.react
vm_entry: main
---
You are a ReAct agent. Reason step-by-step, call tools as needed, then produce a final answer when you have enough information.
Respond ONLY with YAML matching this schema exactly:
{action: call_tool | final_answer | ask_user, tool: tool name (required when action=call_tool), arguments: {key: value} (when action=call_tool), answer: string (required when action=final_answer), question: string (required when action=ask_user), reasoning: optional brief explanation}
Do not use markdown formatting blocks around your YAML response. Return ONLY valid YAML.

```vm
[
  "[]" yaml> "react_trace" shared!
  0 "react_step_count" shared!
  False "react_done" shared!

  [ "react_done" shared@ not ]
  [
    "{}" yaml>
    "request" "initial_request" shared@ dup none? [ drop "task" shared@ dup none? [ drop "" ] [ ] if ] [ ] if dict-set
    "trace" "react_trace" shared@ dict-set
    "last_observation" shared@ dup none? [ drop ] [ "last_observation" swap dict-set ] if
    "cli_context" "formatted_cli_context" shared@ dup none? [ drop "None provided." ] [ ] if dict-set

    "Context (YAML):\n" swap yaml< concat
    "\nAvailable tools:\n" concat
    tool-definitions yaml< concat 
    
    llm-call
    
    [ yaml> "decision" store-set ]
    [
      drop
      "{action: final_answer, answer: 'Error parsing LLM YAML response.'}" yaml> "decision" store-set
    ]
    fallback
    
    "react_trace" shared@
    "decision" store-get list-append
    "react_trace" shared!
    
    "react_step_count" shared@ 1 + "react_step_count" shared!

    "decision" store-get "action" dict-get
    [
      "call_tool" [
        "decision" store-get "tool" dict-get dup none? [ drop "decision" store-get "tool_name" dict-get ] [ ] if
        "decision" store-get "arguments" dict-get dup none? [ drop "{}" yaml> ] [ ] if
        
        "react_step_count" shared@ 30 >= 
        [
          drop drop
          "Max steps reached." answer
          True "react_done" shared!
        ]
        [
          tool-call
          str> "last_observation" shared!
        ]
        if
      ]
      "final_answer" [
        "decision" store-get "answer" dict-get answer
        True "react_done" shared!
      ]
      "ask_user" [
        "decision" store-get "question" dict-get ask-user
        True "react_done" shared!
      ]
      "default" [
        "decision" store-get "answer" dict-get dup none? [ drop "No answer produced." ] [ ] if answer
        True "react_done" shared!
      ]
    ] switch
  ] while
] "main" define
```
