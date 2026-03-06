# Research: Agents to Plugins — Core ReAct Agent Only

**Branch**: `004-agents-to-plugins` | **Date**: 2026-03-05

---

## 1. Current State of core/agents/

**Finding**: The `core/agents/` directory contains no Python source files — only `__init__.py` and a `__pycache__/` folder with stale `.pyc` files for `architect_agent`, `ask_agent`, and `coder_agent`. The actual source files were already physically moved to domain plugins in a prior iteration but the `core/plugin.yaml` manifest still declares those agents pointing to `agents/coder_agent.py` etc. — references that no longer resolve.

**Decision**: The core `plugin.yaml` must be updated immediately. The stale `__pycache__/` in `core/agents/` is removed as cleanup (FR-006).

**Decision**: `agents/react_agent.py` is the only new Python file created in `core/agents/`.

---

## 2. Domain Plugin Agent Naming Gap

**Finding**: The existing domain plugin manifests register agents under different names than the spec requires:

| Plugin dir | Current agent name | Required agent name (spec) | Namespace |
|---|---|---|---|
| `coder/` | `coder` | `coder` | `coder::coder` |
| `architect/` | `architect` | `architect` | `architect::architect` ✅ |
| `asker/` | `ask` | `ask` | `asker::ask` ✅ |

**Decision**: The `coder` plugin's manifest entry must be renamed from `coder` to `coder`. The existing `agents/coder_agent.py` Python file is kept as-is (module path stays `agents/coder_agent.py`); only the manifest key changes.

**Alternatives considered**: Keeping the name `coder` and updating cross-references — rejected because the spec explicitly requires `coder::coder` (FR-003) and all clarifications use `coder` as the agent name.

---

## 3. Tool Bindings for Domain Agents

**Finding**: Domain plugin manifests currently define a minimal local tool subset:
- `coder`: `write_to_file`, `create_directory`, `git_diff` (local copies in `coder/tools/`)
- `architect`: `read_file`, `list_files`, `search_code` (local copies in `architect/tools/`)
- `asker`: `ask_user` (local copy in `asker/tools/`)

The spec requires each agent to have "the same capabilities [...] that `core::X` had" (FR-003/004/005), which means the `coder` agent needs 13 tools (all git + all filesystem + search + execute_command + user_input).

**Decision**: Domain plugin manifests declare the full tool list using cross-plugin references to `core` tools where the tool is not already defined locally. Tools already present locally in the plugin remain as-is; additional tools needed are referenced from `core` using the `core::tool_name` notation (matching the convention from spec 003).

**Rationale**: Cross-plugin references avoid duplicating tool implementations (Constitution Principle III). Local tool overrides are kept for tools the domain plugin has customised.

**Alternatives considered**: Copy all tool implementations into each domain plugin — rejected because this violates Principle III (shared core tools) and creates maintenance debt.

---

## 4. `asker` Plugin Name Inconsistency

**Finding**: The `asker/plugin.yaml` currently declares `name: "ask"`. The directory is named `asker/`. The namespace would be `ask::ask`, not `asker::ask`.

**Decision**: Rename the plugin `name` field to `"asker"` so the namespace becomes `asker::ask`, matching the spec and the clarifications ("A: `ask` agent is registered under the `asker` namespace").

**Alternatives considered**: Keep `name: ask` and update all references to `ask::ask` — rejected because the spec explicitly says "under the `asker` namespace" in multiple places.

---

## 5. ReAct Agent Implementation Pattern

**Finding**: The existing domain agent Python files (e.g., `coder_agent.py`) use a thin `Flow(start=ThinkNode())` pattern with a single node that checks for `_llm_router` in shared store and returns a transition string. The heavy LLM dispatch is done by `AgentRuntime._run_llm_agent()`, not by the Flow itself.

The spec says `core::react` must be a "purpose-built ReAct (Reason → Act → Observe) loop" and MUST NOT delegate to the `single_agent` flow pattern (FR-012).

**Decision**: `react_agent.py` implements a multi-node ReAct loop using native pocketflow `Flow` + `Node`:
- `ReasonNode`: Calls LLM via `_llm_router` from shared store, parses response, determines next step.
- `ActNode`: Executes the tool call via `_tool_runtime` from shared store, stores result as observation.
- `ObserveNode`: Routes back to `ReasonNode` for the next iteration or forwards to `FinalNode`.
- `FinalNode`: Writes `final_answer` to shared store.

The flow is self-contained within the PocketFlow `Flow`; `AgentRuntime._run_pocketflow_agent()` dispatches the flow and treats its return value as the transition.

**Rationale**: Keeps the implementation within pocketflow's native node/flow primitives (Constitution Principle I) while delivering a real Reason→Act→Observe cycle rather than a single-shot LLM call.

**Alternatives considered**: Reuse `_run_llm_agent()` loop from `AgentRuntime` — rejected per FR-012 ("MUST NOT delegate to or reuse the `single_agent` flow pattern") and the spec clarification.

---

## 6. Handoff Reference Format in Manifests

**Finding**: `.pocketcode/plugins/micromanager/plugin.yaml` currently references handoff targets as `core.coder`, `core.architect`, `core.ask` (dot notation). The namespace resolution code (spec 003) uses `::` as the delimiter.

**Decision**: Update micromanager manifest to use `coder::coder`, `architect::architect`, `asker::ask` in fully-qualified form. The coder/architect/asker agent manifests use the same `plugin::agent` form for their mutual handoff references.

**Decision**: Bare short-name handoff references (e.g., `- architect`) are retained in the coder and architect manifests ONLY if the runtime from spec 003 can unambiguously resolve them at startup. If there is any risk of ambiguity, they must be fully qualified. Per the spec clarification: "ambiguous short names cause a startup/validation error; handoff declarations must use the fully-qualified `plugin::agent` form." Therefore **all** handoff targets in this feature use the fully-qualified form.

---

## 7. `single_agent` Flow Removal Scope

**Finding**:
- `core/prompts/flows/single_agent.md` — exists, 4-line file with the old loop description
- `core/prompts/nodes/single_agent/think.md` — exists (node prompt for single_agent)
- `pocketcode.yml` `runtime.agent_runtime_workflow: single_agent` — references the removed flow
- No Python file named `single_agent` was found; the `single_agent` was a YAML/prompt-defined flow

**Decision**: Delete both prompt files. Remove `agent_runtime_workflow` key from `pocketcode.yml` entirely (or set to `react` if the config loader requires a value — to be confirmed during implementation). Update `default_agent` in `pocketcode.yml` to `core::react`.

---

## 8. Integration Test Impact

**Finding**: `tests/integration/test_pocketflow_plugin_discovery.py` likely asserts that `core::coder`, `core::architect`, `core::ask` are discoverable. After migration these move to `coder::coder` etc.

**Decision**: Tests are updated to assert the new agent namespaces. Existing passing assertions for tool discovery, flow execution, and conditional branching remain unchanged.

---

## Resolved Clarifications Summary

| # | Unknown | Resolution |
|---|---|---|
| 1 | Agent files in core/agents? | No .py source files remain there; only __pycache__ stale artifacts |
| 2 | coder agent name mismatch (coder vs coder) | Rename manifest key to `coder` |
| 3 | Tool bindings for domain agents | Full list; cross-plugin refs to core for tools not already local |
| 4 | asker plugin name field | Change `name: ask` → `name: asker` |
| 5 | ReAct implementation approach | New multi-node Flow: ReasonNode→ActNode→ObserveNode→FinalNode |
| 6 | Handoff reference format | Fully-qualified `plugin::agent` form throughout |
| 7 | single_agent removal scope | Delete 2 prompt files; remove/replace pocketcode.yml key |
| 8 | Integration test impact | Update namespace assertions; no new test failures |
