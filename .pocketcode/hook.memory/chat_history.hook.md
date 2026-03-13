---
name: memory.chat_history
description: Append recent saved-session chat history to formatted CLI context.
---

```vm before_turn
6 active-session-transcript-text
dup empty?
[ drop ]
[
  "\n\nRecent chat history:\n" swap concat
  "formatted_cli_context" shared@ dup none?
  [ drop "" ]
  [ ]
  if
  swap concat
  "formatted_cli_context" shared!
] if
```
