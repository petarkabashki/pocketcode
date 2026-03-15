---
name: authoring_agents
description: Guidelines for authoring PocketCoder agents
---

# Authoring Agents in PocketCoder

When authoring agents in PocketCoder, always follow these rules and best practices.

## Concept: Flows vs Agents

- **Flow**: The internal executable runtime model. StackVM should be the default choice for new orchestration-heavy flows. A flow definition provides the base tools, LLM profile, and executable logic.
- **Agent**: A named configuration object (overlay) that governs how a flow behaves during a session. Agents do not define executable logic unless they are self-contained Markdown hybrids. They select and constrain behavior for an existing flow.
- For new work, the canonical path is a **Self-Contained Markdown Agent** that defines both the agent overlay properties and the executable `vm` block in one file.

## Agent Structure
1. **Prefer Self-Contained Markdown Agents**: New agents should typically be self-contained Markdown files that define both the agent's properties and its executable `vm` block.
2. **Naming Convention**: 
   - Write grouped agents to `agent.<group>/<name>.agent.md` (e.g., `agent.review/safe.agent.md`).
   - Write regular agents to `agents/<name>.agent.md`.
3. **Fields**:
   - `name`: Unique agent identifier.
   - `flow`: Target flow name (required unless using `extends` or making a self-contained agent with a `vm` block).
   - `description`: Human-readable description.
   - `llm_profile`: LLM profile override (defaults to inherited or global default).
   - `tools`: Tool allowlist (list of canonical dotted ids like `core.read_file`). `tools: []` means allow no base tools.
   - `skills`: Default enabled skills (list of skill names).
   - `extra_prompts`: Additional prompt references (file paths like `prompts/review.md` or `prompt:` refs).
   - `hooks`: Ordered hook refs (e.g. `resource_root.pocketcode.memory.chat_history`) mixed into the lifecycle.
   - `commands`: Declarative command aliases exported by the agent.
   - `tool_confirmation`: Confirmation defaults and per-tool overrides (e.g. `default: confirm`, `overrides: { core.execute_command: deny }`).
   - `extends`: Parent agent name to inherit from.

## Inheritance Rules
Authored agents are sparse and do not automatically copy flow defaults into their stored fields.
- `flow`: Inherited from `extends` when omitted.
- `tools`, `skills`, and `hooks`: Replaced entirely if explicitly defined in the child agent. Inherited from parent when `extends` is used.
- `extra_prompts` and `inline_prompt` (the markdown body): *Appended* to the parent's prompts.
- `commands`: Merged by command `name`, with child winning.
- `tool_confirmation`: Merged with child values winning. `tool_confirmation.default` overrides the parent if present.
- Synthesised default agents (automatically created for every flow) inherit the flow's base `llm_profile` and `tools`.

## Resolution and Precedence
- **Agent Precedence**: (1) Workspace agent profiles, (2) Synthesised defaults built from flow definitions.
- **LLM Tier Order**: Session overrides -> ... -> Active agent `llm_profile` -> Flow definition `llm_profile` -> Default LLM profile.
- **Tool Confirmation Tier Order**: Session tool overrides -> Active profile tool overrides -> ... -> Active profile default -> ... -> Global default. Tools outside the active allowlist are denied before confirmation is evaluated.

## Self-Contained VM Block
If writing a self-contained agent, include `execution_mode: vm`, `vm_entry: <word>`, or `vm_source` in the YAML frontmatter. Provide the StackVM source code inside a fenced `vm` block following the markdown body.

## Example Self-Contained Agent
```md
---
name: example-agent
description: A basic self-contained agent.
execution_mode: vm
vm_entry: main
tools:
  - core.read_file
extra_prompts:
  - prompts/example.md
---
You are an example helpful agent.

` ` `vm
[ "main" "router.handle" handoff ] "main" define
` ` `
```
*(Note: Do not use spaces between backticks in fenced blocks; they are separated here to avoid escaping issues.)*
