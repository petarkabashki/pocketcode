# Flows And Agents

This document describes the current relationship between executable flows and inheritable agents.

For the canonical Markdown file formats for flows and agents, see `markdown_assets.md`.

## One Executable Model, Multiple Agent Layers

PocketCoder executes flows. Agents do not replace flows; they configure how a selected flow runs. For new work, the preferred shape is a self-contained Markdown agent that contains both the VM program and the authored agent metadata.

The current stack is:

1. flow definition
2. active agent
3. active hook overlays referenced by the agent
4. optional enabled skills
5. session overrides from the CLI or Textual UI

## Flow Authoring

PocketCoder supports two canonical executable flow authoring paths:

1. StackVM flow authored in self-contained Markdown
2. PocketFlow factory authored in Python

StackVM should be the default choice for new orchestration-heavy flows. PocketFlow remains the escape hatch for flows that genuinely need Python-native objects, custom node classes, or logic that would be awkward to express in VM words.

### PocketFlow Factories

The canonical PocketFlow-authored path is:

1. implement a PocketFlow factory in Python
2. reference it from a self-contained Markdown flow

Example:

```python
from pocketflow import Flow, Node


class ThinkNode(Node):
    def prep(self, shared):
        return shared.get("task", "")

    def exec(self, task):
        return task

    def post(self, shared, prep_res, exec_res):
        shared["result"] = exec_res
        return "done"


def create_flow() -> Flow:
    return Flow(start=ThinkNode())
```

Markdown registration:

```yaml
name: analyst
module: analyst.py
entry_fn: create_flow
description: Analyze the current workspace.
```

Markdown can also author executable flows directly. In that case the Markdown file contributes the flow fields, and PocketCoder currently supports two execution backends from that one authoring surface:

- Python factory flow via `module` plus `entry_fn`
- StackVM flow when the file contributes fenced `vm` or `stackvm` blocks, or explicit `vm_*` source fields

Graph-authored Markdown flows are no longer supported by the runtime loader; migrate those definitions to StackVM. The StackVM path is the preferred executable Markdown surface for multi-step orchestration while still running inside the same shared-store and handoff contract. It does not replace handwritten Python factories when you need custom logic tightly coupled to Python objects or richer PocketFlow node classes.

For new work, prefer a single Markdown file that contains:

- front matter for tool refs, prompt refs, handoff config, and optional `tool_files`
- Markdown body text for the system prompt
- fenced `vm` blocks for the executable program

`tool_files` entries are resolved relative to that Markdown file, loaded as Python tool modules, and registered into the same namespace before the flow is finalized. The preferred convention for those helper modules is `*.tool.py`. When explicit `tool_files` and prompt-file fields are omitted, PocketCoder also auto-loads sibling `<name>.tool.py` and `<name>.prompt.md` files beside the Markdown program.

Configured workspace discovery paths in `runtime.workspace_paths` add two canonical Markdown flow paths:

1. use a plain namespace folder such as `.github/`, then add `*.md`, `*.tool.py`, and `*.prompt.md` files inside it
2. use a flat namespace-pack root such as `.pocketcode/`, then add files like `coder.coder.md`, `coder.git.tool.py`, and `coder.system.prompt.md`

In both cases PocketCoder registers each executable Markdown file as a flow under `<namespace>.<name>`.

## What A Flow Definition Can Do

A flow definition can supply:

- a PocketFlow `flow_instance`
- StackVM source metadata such as `vm_source`, `vm_entry`, `vm_module`, and `vm_file`
- an `llm_profile`
- a base tool list
- handoff targets and policies
- pre, step, and post handlers
- base prompt text and prompt source files
- an inline default agent

The flow is the authoritative base layer for execution.

## Agents

An agent is a named `CompositeAgent` that targets one flow.

Agents can change:

- `llm_profile`
- `inline_prompt`
- `extra_prompts`
- `hooks`
- `skills`
- `tools`
- `tool_confirmation`

Agents do not define executable graph logic unless they are self-contained Markdown hybrids. In the common case they select and constrain behavior for an existing flow.

## Agent Sources

Current authored-agent sources are:

1. inline `default_agent` inside a flow definition
2. workspace agent profiles in discovered resource roots, including legacy flat files and grouped `agent.<group>/` collections
3. synthesised fallback agent created from the flow definition

Effective precedence is:

1. manifest-defined agents
2. workspace agents
3. synthesised defaults

## Inheritance

Authored agents can inherit from other agents with `extends`.

Current behavior:

- authored agents stay sparse and do not automatically copy flow defaults into their stored fields
- `flow` may be omitted when `extends` is present
- omitted `llm_profile`, `hooks`, `skills`, and `tools` inherit from the parent agent
- parent and child `inline_prompt` / `extra_prompts` are appended in that order
- `tool_confirmation` merges with child values winning
- synthesised default agents still carry the flow's base `llm_profile` and `tools`

This gives the runtime a two-part model:

1. executable flow
2. inheritable agent overlay chain with reusable hook refs

### Self-Contained Hybrid Agents

Markdown agents can also define their own flow logic directly in the same file. When the system detects flow fields (like `vm_source` or `module`) in an agent `.md` file, it automatically registers an embedded flow and points the agent to it.

This pattern is ideal for simple, portable agents where personality and control logic are tightly coupled.

Do not confuse those `.agent.*` files with configured namespace assets. In plain namespace folders and flat namespace-pack roots, plain executable `.md` files are treated as runtime flows, not as agent overlays.

## Synthesised Defaults

Every loaded flow gets a synthesised default agent if no higher-precedence agent replaces that name.

That synthesised agent:

- uses the flow's qualified name as its own name
- targets the same flow
- inherits the flow's `llm_profile`
- inherits the flow's tool list

## Workspace Agent Schema

Current workspace agent schema:

```yaml
name: my-review-profile
flow: core.react
description: Review-focused profile
llm_profile: fast-review
hooks:
  - workspace.memory.default
skills:
  - python-testing
tools:
  - core.read_file
  - core.search_code
extra_prompts:
  - prompts/review.md
tool_confirmation:
  default: confirm
  overrides:
    core.execute_command: deny
```

Current inheriting schema:

```yaml
name: my-review-profile-safe
extends: my-review-profile
hooks:
  - workspace.shortcut.cache
tools:
  - core.read_file
tool_confirmation:
  default: confirm
```

Notes:

- `flow` is required unless `extends` is present.
- `hooks` omitted means inherit the parent hook list when `extends` is used; otherwise they inherit the synthesised default chain.
- `skills` omitted means fall back to the global Textual skill defaults for that session.
- `tools` omitted means inherit the parent agent tools when `extends` is used; otherwise they inherit the flow tool surface through the synthesised default chain.
- `tools: []` means allow no base tools.
- workspace agents may also be authored as Markdown, where front matter carries the structured fields and the body becomes `inline_prompt`.

## Skills Extend The Active Profile

Skills do not replace the active agent either. They extend it by adding:

- inline prompt guidance
- extra prompt files
- references to existing tools
- skill-provided tool modules

Skill prompt text is appended after the active agent prompt content.

## Effective Prompt Composition

For a given flow turn, the effective prompt is:

1. flow system prompt
2. active agent inline prompt
3. active agent extra prompt files
4. enabled skill inline prompts
5. enabled skill extra prompt files

## Effective Tool Surface

For a given flow turn, the effective tool surface is:

1. flow tools
2. filtered by active agent allowlist when present
3. extended by enabled skill references to existing tools
4. extended by enabled skill-provided tools

## Programmatic Flow Runtime Helpers

When a PocketFlow `flow_instance` or StackVM-backed flow runs, the runtime injects services into the shared store, including:

- `_llm_router`
- `_tool_runtime`
- `_agent_llm_profile`
- `_agent_system_prompt`
- `_agent_tool_definitions`
- `_registry`

These are runtime conveniences, not part of the manifest schema.

## React Agent Memory Model

The built-in `core.react` flow currently has two distinct memory layers:

- per-run working memory in the shared store, primarily `react_trace`, `last_observation`, and the current `initial_request`
- saved-session transcript persistence managed by the engine and exposed through `/memory` and `/session` commands

Current behavior is intentionally narrow:

- the React prompt receives the current request, the in-flight ReAct trace, the latest observation, and formatted CLI context
- the saved-session transcript is persisted after each run, but it is not automatically injected back into `core.react` as prompt context on later turns

The workspace now ships a generic hook-based simple-memory path for agents that already consume `formatted_cli_context`:

- `workspace.memory.chat_history` runs in `before_turn`
- it reads the active saved-session transcript through the StackVM host transcript helpers
- it appends the last six transcript entries as a compact `Role: content` block on `formatted_cli_context`

So the runtime already has transcript persistence, and simple recent-history memory can be added generically through hooks. `core.react` now uses that hook through the workspace `my-react` agent profile, but richer long-term retrieval still requires explicit engine or flow-level design beyond this recency-based pattern.

## Handoffs

A flow can hand off to other flows through `handoff_agents` and optional handoff policy configuration.

Current handoff behavior supports:

- target flow selection
- handoff-level LLM overrides
- whole-context or delegated-context mode
- optional return-to-caller behavior

## Authoring Guidance

When documenting or implementing new behavior, keep these distinctions explicit:

- self-contained Markdown VM programs are the preferred way to author executable flows
- flows are the internal executable runtime model
- agents are named overlays for flows and may inherit from one another
- skills are additive session extensions

That separation is the current canonical model in the codebase.
