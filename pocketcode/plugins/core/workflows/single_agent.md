---
name: single_agent
description: Agent runtime loop with tool calling and recursive handoff support.
start: start
default_agent: Coder
prompt_file: prompts/flows/single_agent.md
nodes:
  start:
    use: default_start
  think:
    prompt_file: prompts/nodes/single_agent/think.md
  handoff:
    use: default_handoff
  run_tool:
    use: default_tool
  output:
    use: default_output
  end:
    use: default_end
---

```dot
digraph single_agent {
  start [kind="start"];
  think [kind="agent"];
  handoff [kind="handoff"];
  specialist [kind="flow" flow="single_agent"];
  run_tool [kind="tool"];
  output [kind="output"];
  end [kind="end"];

  start -> think [label="continue"];

  think -> run_tool [label="call_tool"];
  think -> handoff [label="handoff"];
  think -> output [label="final_answer"];
  think -> output [label="ask_user"];
  think -> output [label="error"];

  run_tool -> think [label="success"];
  run_tool -> output [label="error"];

  handoff -> specialist [label="continue"];
  handoff -> output [label="error"];

  specialist -> think [label="continue"];
  specialist -> output [label="error"];

  output -> end [label="done"];
}
```
