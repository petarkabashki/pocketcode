---
name: pocketcode-tools-runtime
description: Use when creating or editing PocketCoder tools and their runtime behavior. Covers BaseTool, callable tools, workspace tools, skill tools, tool schemas, confirmation policies, allowlists, and managed subprocess execution.
tools:
  - core.read_file
  - core.search_code
---
Use this skill for tool implementation and runtime behavior.

Read first:
- `references/tools-runtime.md`

Use it when the task touches:
- namespace-local tools
- workspace tools
- skill-owned tools
- tool confirmation
- tool execution mode
- runtime allowlist behavior

When in doubt, match the real runtime path from `ToolRuntime` and `AgentRuntime` instead of designing a cleaner but incompatible abstraction.
