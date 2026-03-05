# Data Model: Agents to Plugins — Core ReAct Agent Only

**Branch**: `004-agents-to-plugins` | **Date**: 2026-03-05

---

## Entities

### 1. Plugin

A self-contained directory registered in `pocketcode.yml` (or in `.pocketcode/plugins/`). Each plugin has exactly one `plugin.yaml` manifest.

| Field | Type | Constraints |
|-------|------|-------------|
| `name` | string | Unique across all loaded plugins. Becomes the first segment of namespaced references (`name::agent`). |
| `description` | string | Human-readable summary. |
| `schema_version` | int | Must be `1`. |
| `tools` | map[str→path:Class] | Optional. Local tool registrations. |
| `agents` | map[str→AgentManifestEntry] | Optional. Agent registrations. |

**Instances after migration**:

| Plugin dir | `name` | Agents registered |
|---|---|---|
| `core/` | `core` | `react` |
| `coder/` | `coder` | `coder` |
| `architect/` | `architect` | `architect` |
| `asker/` | `asker` | `ask` |
| `micromanager/` | `micromanager` | `micromanager` |

---

### 2. AgentManifestEntry

The YAML block within a `plugin.yaml` that registers one agent.

| Field | Type | Constraints |
|-------|------|-------------|
| `description` | string | Human-readable summary of agent role. |
| `module` | path | Relative path to Python file inside the plugin dir. Must physically exist in that plugin's directory (FR-006). |
| `entry_fn` | string | Name of the callable in `module` that returns a `pocketflow.Flow`. |
| `llm_profile` | string | Must match a key in `pocketcode.yml → llm.profiles`. |
| `tools` | list[str] | Tool names. Bare names are resolved local-first, then `core` namespace. Cross-plugin refs use `plugin::tool`. |
| `handoff_agents` | list[str] | Fully-qualified `plugin::agent` references (FR-007). Bare names are forbidden after this migration. |
| `prompts` | list[path] | Optional. Relative paths to prompt markdown files inside the plugin dir. |

---

### 3. AgentDefinition (runtime model — `pocketcode/core/runtime_models.py`)

Populated by the manifest loader at startup; validated against the registered agent registry.

| Field | Type | Source |
|-------|------|--------|
| `name` | str | manifest key |
| `namespace` | str | `plugin_name::agent_name` |
| `description` | str | manifest |
| `system_prompt` | str | loaded from `prompts[0]` if specified |
| `llm_profile` | str | manifest |
| `tools` | list[str] | manifest (resolved) |
| `handoff_agents` | list[str] | manifest (validated at startup) |
| `flow_instance` | Flow &#124; None | instantiated from `module:entry_fn()` |
| `metadata` | dict | `plugin_name`, `plugin_root` |

**Validation rules** (enforced on startup):
- All `handoff_agents` entries must resolve to a registered `AgentDefinition`. If not found, startup fails with a descriptive message naming the missing target and its suggested replacement (clarification Q1).
- Duplicate short names across loaded plugins raise a startup/validation error requiring fully-qualified form (FR-007).

---

### 4. ReActAgent (`core/agents/react_agent.py`)

A PocketFlow `Flow` composed of four `Node` subclasses.

```
ReasonNode ──(call_tool)──► ActNode ──► ObserveNode ──(loop)──► ReasonNode
    │                                        │
    │(final_answer)                          │(final_answer)
    ▼                                        ▼
 FinalNode                               FinalNode
```

| Node | Responsibility |
|------|---------------|
| `ReasonNode` | Calls `_llm_router` with current context + tool definitions. Parses YAML response. Returns transition: `call_tool`, `final_answer`, or `ask_user`. |
| `ActNode` | Executes the tool via `_tool_runtime`. Stores result as `last_observation` in shared store. |
| `ObserveNode` | Appends observation to reasoning trace in shared store. Routes back to `ReasonNode` or to `FinalNode`. |
| `FinalNode` | Writes `final_answer` (or `question_to_ask`) to shared store. Returns `"final_answer"` transition. |

**State in shared store** (additions by react agent):

| Key | Type | Description |
|-----|------|-------------|
| `react_trace` | list[dict] | Accumulated Reason/Act/Observe steps |
| `last_observation` | str | Most recent tool result as string |
| `react_step_count` | int | Guard counter against infinite loops |

**Validation rules**:
- `react_step_count` must not exceed `max_agent_steps` (from runtime config, default 64).
- `_llm_router` must be present in shared store; if absent, agent raises `RuntimeError`.

---

### 5. Handoff Reference

A reference from one agent manifest to another agent it may transfer control to.

| Form | Example | Validity after migration |
|------|---------|--------------------------|
| Fully-qualified | `coder::coder` | ✅ Valid |
| Bare short name | `coder` | ❌ Forbidden in manifests after migration (FR-007) |
| Old dot notation | `core.coder` | ❌ Stale — causes startup error |

---

## State Transitions

### Agent Registry (at startup)

```
Plugin dirs loaded
    │
    ▼
plugin.yaml parsed for each plugin
    │
    ▼
AgentManifestEntry validated:
  - module path exists within plugin dir
  - entry_fn callable returns pocketflow.Flow
  - handoff_agents all resolvable → error if not
    │
    ▼
AgentDefinition registered in NamespaceRegistry
  key: "plugin::agent"
```

### Runtime Handoff Resolution

```
Agent produces {action: handoff, agent: "coder::coder"}
    │
    ▼
AgentRuntime._run_handoff()
  lookup "coder::coder" in plugins.agents
    │
  ┌─┴─ found ──► set active_agent = "coder::coder" ──► next turn
  └─── not found ──► error_message with suggestion
```

---

## Removal Checklist

Items that must be absent after the migration (verified by SC-* acceptance criteria):

| Item | Location | Removed by |
|------|----------|-----------|
| `coder` agent entry | `core/plugin.yaml` | core manifest update |
| `architect` agent entry | `core/plugin.yaml` | core manifest update |
| `ask` agent entry | `core/plugin.yaml` | core manifest update |
| `agents/coder_agent.py` | `core/agents/` | already absent; `__pycache__` cleaned |
| `agents/architect_agent.py` | `core/agents/` | already absent; `__pycache__` cleaned |
| `agents/ask_agent.py` | `core/agents/` | already absent; `__pycache__` cleaned |
| `prompts/flows/single_agent.md` | `core/prompts/flows/` | file deletion |
| `prompts/nodes/single_agent/think.md` | `core/prompts/nodes/single_agent/` | file deletion |
| `agent_runtime_workflow: single_agent` | `pocketcode.yml` | config update |
| `default_agent: Ask` | `pocketcode.yml` | config update → `core::react` |
| `core.coder`, `core.architect`, `core.ask` refs | `micromanager/plugin.yaml` | manifest update |
