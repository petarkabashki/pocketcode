# Tasks: Unified Plugin Namespace Architecture

**Input**: Design documents from `specs/003-unified-plugin-namespace/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Unit tests are included where explicitly required by the spec (new infrastructure modules need test coverage to validate collision/resolution contracts). Integration tests are the existing suite — they must pass unmodified at each checkpoint.

**Organisation**: Tasks are grouped by user story to enable independent implementation and testing of each increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no blocking dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Exact file paths are included in every task description

---

## Phase 1: Setup

**Purpose**: Create directory structure and package init files that all subsequent tasks write into.

- [ ] T001 Create `pocketcode/plugins/core/tools/__init__.py` (empty package init — makes `core/tools/` a valid Python package)
- [ ] T002 [P] Create `pocketcode/plugins/core/agents/__init__.py` (empty — home for core agent PocketFlow factories)
- [ ] T003 [P] Create `tests/unit/__init__.py` (empty — enables pytest discovery for new unit tests)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement the two new core modules and update the runtime model. These are pure additive changes — no existing code is modified — and they block all user story phases.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T004 [P] Create `pocketcode/core/namespace_registry.py` — implement full `NamespaceRegistry[T]` class with three-tier store (`_ns`, `_flat`, `_bare`), `register()`, `unregister_plugin()`, `resolve()` (qualified + unqualified + `context_plugin` local-first), `list_all()`, `list_by_plugin()`, `plugins()`, `items()`, `__contains__()`, `snapshot()`, `RegistryError`, and `RegistryHolder` with `get()` + `swap()` per `contracts/registry-api.md`
- [ ] T005 [P] Create `pocketcode/core/manifest_loader.py` — implement `ParsedManifest` dataclass, `ManifestSchemaError(ValueError)`, `load_manifest(path: Path) -> ParsedManifest`, `_validate_schema_version()`, `_load_agent_yaml_with_warning()` shim (returns `schema_version=0`), `_warn_legacy_sections()` for `components/workflows/node_definitions/flows/modes`, per `contracts/manifest-v1.md`
- [ ] T006 [P] Update `pocketcode/core/runtime_models.py` — add `module: Optional[str] = None`, `entry_fn: Optional[str] = None`, and `flow_instance: Optional[Flow] = None` fields to `AgentDefinition` (or whichever dataclass holds agent metadata); keep all existing fields intact; `flow_instance` is populated **eagerly** during `PluginManager._load_plugin()` by calling `entry_fn()` immediately after registration — if `entry_fn()` raises, the agent is skipped and `ERROR` is logged

**Checkpoint**: `python -c "from pocketcode.core.namespace_registry import NamespaceRegistry; from pocketcode.core.manifest_loader import load_manifest"` completes without error.

---

## Phase 3: User Story 1 — Core Tools Consolidated in Core Plugin (Priority: P1) 🎯 MVP

**Goal**: All built-in tool implementations live in `pocketcode/plugins/core/tools/`; the core plugin is fully self-contained; `pocketcode/tools/` is retained as a re-export-only shim library.

**Independent Test**: Start the system with only the core plugin active. Confirm all previously available core tools (read/write file, git, shell, search, user-input) are registered and functional. Confirm `from pocketcode.tools.system import execute_shell_command` still resolves.

### Implementation for User Story 1

- [ ] T007 [P] [US1] Copy `pocketcode/tools/filesystem.py` → `pocketcode/plugins/core/tools/filesystem.py`; update any intra-package imports from `pocketcode.tools.*` to `pocketcode.plugins.core.tools.*`
- [ ] T008 [P] [US1] Copy `pocketcode/tools/system.py` → `pocketcode/plugins/core/tools/system.py`; update intra-package imports
- [ ] T009 [P] [US1] Copy `pocketcode/tools/git.py` → `pocketcode/plugins/core/tools/git.py`; update the `execute_shell_command` import to `from pocketcode.plugins.core.tools.system import execute_shell_command` (canonical, not the shim)
- [ ] T010 [P] [US1] Copy `pocketcode/tools/search.py` → `pocketcode/plugins/core/tools/search.py`; update intra-package imports
- [ ] T011 [P] [US1] Copy `pocketcode/tools/user_input.py` → `pocketcode/plugins/core/tools/user_input.py`; update intra-package imports
- [ ] T011a [P] [US1] Copy `pocketcode/tools/context_elephant_store_tools.py` → `pocketcode/plugins/core/tools/context_elephant_store_tools.py`; update any intra-package imports; **note**: this file contains 5 `BaseTool` subclasses (`ReadContextElephantStoreFileTool`, `WriteContextElephantStoreFileTool`, `AppendToContextElephantStoreFileTool`, `GetContextElephantStoreSummaryTool`, `CheckContextElephantStoreStatusTool`) and is NOT currently registered in any `plugin.yaml` — do not add it to core tool registrations without an explicit decision; the wrapper in T011b is still required because code may import from the old path
- [ ] T011b [P] [US1] Replace `pocketcode/tools/context_elephant_store_tools.py` with a backward-compat re-export wrapper forwarding all public `BaseTool` subclasses and exception types from `pocketcode.plugins.core.tools.context_elephant_store_tools` (depends on T011a)
- [ ] T012 [US1] Replace `pocketcode/tools/filesystem.py` with a backward-compat re-export wrapper: `from pocketcode.plugins.core.tools.filesystem import *` plus explicit `__all__` listing every public symbol (depends on T007)
- [ ] T013 [P] [US1] Replace `pocketcode/tools/system.py` with re-export wrapper — MUST re-export both `ExecuteCommandTool` and bare function `execute_shell_command` (consumed by `koder/tools/git.py`) (depends on T008)
- [ ] T014 [P] [US1] Replace `pocketcode/tools/git.py` with re-export wrapper (depends on T009)
- [ ] T015 [P] [US1] Replace `pocketcode/tools/search.py` with re-export wrapper (depends on T010)
- [ ] T016 [P] [US1] Replace `pocketcode/tools/user_input.py` with re-export wrapper (depends on T011)
- [ ] T017 [US1] Update `pocketcode/plugins/core/plugin.yaml` — change all tool entry values from dotted-module paths (`pocketcode.tools.filesystem.ReadFileTool`) to file-relative format (`tools/filesystem.py:ReadFileTool`); add `schema_version: 1` as the first key; remove or comment out `components:`, `workflows:`, and `node_definitions:` legacy sections
- [ ] T018 [US1] Run `pytest tests/integration/` — must pass without any test file modifications (SC-001 first checkpoint); fix any import breakages in wrappers before proceeding

**Checkpoint**: Core plugin loads; all core tools register; `pytest tests/integration/` is green; `from pocketcode.tools.system import execute_shell_command` resolves in a fresh interpreter.

---

## Phase 4: User Story 4 — No Regressions for Existing Agents (Priority: P1)

**Goal**: Core non-orchestrating agents (Coder, Architect, Ask) are expressed as PocketFlow `Flow` factories and registered under the new agents namespace. The micromanager — which requires `shared["_registry"]` for cross-agent delegation — is migrated in Phase 5 after the NamespaceRegistry is wired into the runtime.

**Independent Test**: Run the existing `tests/integration/` suite against the refactored system for the three core agents. Tests that exercise micromanager orchestration will be validated in the Phase 5 checkpoint after `shared["_registry"]` is populated.

### Implementation for User Story 4

- [ ] T019 [US4] Create `pocketcode/plugins/core/agents/coder_agent.py` — `create_flow() -> Flow` factory; port the Coder agent's logic into a PocketFlow `Flow` + `Node` graph; source: `core/plugin.yaml` `components: Coder:` block, associated workflow YAML files in `core/workflows/`, and current `agent_runtime.py` execution paths
- [ ] T020 [P] [US4] Create `pocketcode/plugins/core/agents/architect_agent.py` — `create_flow() -> Flow` factory for **`core.Architect`** (the planning component currently declared in `core/plugin.yaml` under `components: Architect:`); **no collision with `arkitekt` plugin**: `arkitekt` registers under its own plugin namespace with local name `arkitekt`, while `core.Architect` has local name `Architect` — different bare names, no FR-006 ambiguity
- [ ] T021 [P] [US4] Create `pocketcode/plugins/core/agents/ask_agent.py` — `create_flow() -> Flow` factory for the Ask agent; source: `core/plugin.yaml` `components: Ask:` block
- [ ] T023 [US4] Update `pocketcode/plugins/core/plugin.yaml` — add `agents:` block with entries for `coder`, `architect`, `ask`; each with `module:` pointing to the new factory file and `entry_fn: create_flow`; include `llm_profile`, `tools`, and `prompts` per each agent's existing configuration; **depends on T017** (schema_version and tool refs must already be updated before adding the agents: block)
- [ ] T025 [US4] Run `pytest tests/integration/` against the three core agents (Coder, Architect, Ask); confirm tests pass unmodified for those flows (SC-001 P1 partial gate); micromanager integration tests are deferred to T030 in Phase 5

**Checkpoint**: Core agents Coder, Architect, and Ask load and execute correctly via PocketFlow factories. Core `plugin.yaml` has `schema_version: 1` and an `agents:` block. `pytest tests/integration/` passes for non-micromanager flows.

---

## Phase 5: User Story 2 — Namespace-Qualified Resource References (Priority: P2)

**Goal**: `PluginManager` delegates all storage to `NamespaceRegistry` instances; every resource is addressable as `plugin_name.resource_name`; hot-reload uses snapshot-swap; collision detection is live. The micromanager agent and its manifest are also migrated here because it relies on `shared["_registry"]` which is wired in this phase.

**Independent Test**: Load two plugins that each define a tool with the same local name. Confirm `plugin_a.tool` and `plugin_b.tool` each resolve to their respective implementations. Confirm that resolving the bare `tool` name emits a `WARNING` and resolves when only one plugin owns it, and raises `RegistryError` when two plugins own it.

### Implementation for User Story 2

- [ ] T022 [US4→US2] Create `pocketcode/plugins/micromanager/agents/micromanager_agent.py` — `create_flow() -> Flow` factory; orchestrating Flow whose nodes delegate to sub-agents by resolving `core.Coder`, `core.Architect`, etc. from `shared["_registry"].agents`; **moved from Phase 4** because `shared["_registry"]` is only populated after T028 wires the registry into the session shared store
- [ ] T024 [US4→US2] Convert `pocketcode/plugins/micromanager/agent.yaml` → `pocketcode/plugins/micromanager/plugin.yaml` — add `schema_version: 1`; add `agents:` block for `micromanager` with `module: agents/micromanager_agent.py`, `entry_fn: create_flow`; migrate existing tools and prompts entries (depends on T022)
- [ ] T026 [US2] Refactor `pocketcode/core/plugin_manager.py` — replace `self.tools` (dict) with `self.tools: NamespaceRegistry[Callable]`; replace `self.agents` with `self.agents: NamespaceRegistry[AgentDefinition]`; add `self.prompts: NamespaceRegistry[str]`; update `_load_plugin()` to call `manifest_loader.load_manifest()` and then `self.tools.register(plugin, name, impl)` / `self.agents.register(plugin, name, def)` / `self.prompts.register(plugin, name, content)` per each loaded resource; catch `RegistryError` and log at `ERROR` level, skipping offending plugin; add `RegistryHolder` instance as `self._holder`; add plugin-namespace-collision check in `load()` before any `register()` calls
- [ ] T027 [P] [US2] Update `pocketcode/core/watcher.py` — add `_rebuild_in_progress: threading.Event` flag; on file-change callback, skip if rebuild already in progress; otherwise set flag, build new `PluginManager` snapshot outside the lock, call `self._holder.swap(new_pm)`, then clear flag; existing `_debounced_enqueue` (500 ms timer) is retained as-is
- [ ] T028 [US2] Update `pocketcode/core/workflow_runtime.py` — remove any YAML-workflow-specific execution branches; route all agent invocations through `registry = holder.get(); flow = registry.agents.resolve(agent_qname).flow_instance; flow.run(shared)` pattern; ensure `shared["_registry"]` is populated at session start with the registry snapshot
- [ ] T029 [P] [US2] Write `tests/unit/test_namespace_registry.py` — unit tests covering: `register()` success; `RegistryError` on qualified-name collision; `resolve()` with qualified ref; `resolve()` with unqualified ref + 1 owner emits `WARNING`; `resolve()` with unqualified ref + 2 owners raises `RegistryError`; `resolve()` with `context_plugin` resolves local name first; `unregister_plugin()` removes all entries; `snapshot()` returns deep copy; `list_all()`, `list_by_plugin()`, `plugins()`, `__contains__()`; **prompt registry coverage**: `prompts` `NamespaceRegistry[str]` — `resolve("plugin.prompt_name")` succeeds; `RegistryError` when plugin is not loaded; `WARNING` emitted for unqualified cross-plugin prompt ref with 1 owner; `RegistryError` for unqualified prompt ref matching 2+ plugins
- [ ] T030 [US2] Run `pytest tests/` — all unit tests (T029) pass; all integration tests still pass; fix any callsites that depended on the old flat dict API (e.g., `plugin_manager.tools["name"]` → `plugin_manager.tools.resolve("name")`)

**Checkpoint**: Qualified references (`core.read_file`, `koder.write_to_file`) resolve correctly across all loaded plugins. Collision between two plugins emits `ERROR` and skips the second plugin. Hot-reload within 5 s (SC-007). Micromanager loads, its factory resolves `core.Coder` from `shared["_registry"].agents`. `pytest tests/` is fully green including any micromanager integration tests.

---

## Phase 6: User Story 3 — Single Unified Plugin Manifest Format (Priority: P3)

**Goal**: All remaining plugins (`koder`, `arkitekt`, `asker`) are converted from `agent.yaml` to `plugin.yaml` with `schema_version: 1` and their agents declared via `module:` + `entry_fn:`.

**Independent Test**: Convert one existing plugin from each format; start the system; confirm it loads both with identical runtime behavior and zero `WARNING` / `ERROR` log records about legacy format.

### Implementation for User Story 3

- [ ] T031 [US3] Create `pocketcode/plugins/koder/agents/koder_agent.py` — `create_flow() -> Flow` factory; port koder's personality, tools, and workflow logic into a PocketFlow `Flow` + `Node` graph
- [ ] T032 [US3] Convert `pocketcode/plugins/koder/agent.yaml` → `pocketcode/plugins/koder/plugin.yaml` — add `schema_version: 1`; migrate `tools:` list-of-dicts to `tools:` dict format (`local_name: tools/file.py:ClassName`); add `agents:` block with `koder: {module: agents/koder_agent.py, entry_fn: create_flow, ...}`; migrate `personality.system_prompt` → `prompts.system`; remove `workflows:` list
- [ ] T033 [P] [US3] Create `pocketcode/plugins/arkitekt/agents/arkitekt_agent.py` — `create_flow() -> Flow` factory for the Architect plugin
- [ ] T034 [P] [US3] Convert `pocketcode/plugins/arkitekt/agent.yaml` → `pocketcode/plugins/arkitekt/plugin.yaml` (schema_version: 1, agents: block, tools dict, prompts)
- [ ] T035 [P] [US3] Create `pocketcode/plugins/asker/agents/asker_agent.py` — `create_flow() -> Flow` factory for the Ask/Asker plugin
- [ ] T036 [P] [US3] Convert `pocketcode/plugins/asker/agent.yaml` → `pocketcode/plugins/asker/plugin.yaml` (schema_version: 1, agents: block, tools dict, prompts)
- [ ] T037 [P] [US3] Write `tests/unit/test_manifest_loader.py` — unit tests covering: `load_manifest()` success for valid `plugin.yaml`; `ManifestSchemaError` on missing `schema_version`; `ManifestSchemaError` on unknown `schema_version` value; `agent.yaml` detection emits `WARNING` and returns `schema_version=0`; `_warn_legacy_sections()` emits `WARNING` for `components:`, `workflows:`, `node_definitions:`; missing `module` or `entry_fn` in an agent block raises `ManifestSchemaError`
- [ ] T038 [US3] Run `pytest tests/` — all unit tests (T037) pass; all integration tests pass; no `agent.yaml` files remain in `plugins/` (verify with `find pocketcode/plugins -name agent.yaml`)

**Checkpoint**: Zero `agent.yaml` files remain. All plugins load via `plugin.yaml` with `schema_version: 1`. No legacy-section warnings at startup. `pytest tests/` is fully green.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Cleanup, documentation, and final end-to-end validation across all user stories.

- [ ] T039 [P] Remove stale workflow YAML files from `plugins/*/workflows/` directories that have been superseded by PocketFlow agent factories (verify no remaining files are referenced anywhere in the codebase before deleting)
- [ ] T040 [P] Update `docs/plugin_architecture.md` — replace workflow-centric content with the unified plugin model: one manifest, one namespace, agents = PocketFlow flows
- [ ] T041 [P] Update `docs/pocketflow_agents.md` — reflect the final architecture where agents supersede workflows completely; link to `quickstart.md`
- [ ] T042 [P] Update `docs/README.md` and `readme.md` — add plugin authoring section with link to `specs/003-unified-plugin-namespace/quickstart.md`
- [ ] T043 Run the `quickstart.md` end-to-end validation — follow every step in `specs/003-unified-plugin-namespace/quickstart.md` to create a fresh minimal plugin; confirm it loads, its tool is discoverable, and its agent `create_flow` returns a runnable `Flow`

---

## Dependencies & Execution Order

### Phase Dependencies

| Phase | Depends On | Can Start |
|---|---|---|
| Phase 1 — Setup | Nothing | Immediately |
| Phase 2 — Foundational | Phase 1 complete | After T001-T003 |
| Phase 3 — US1 (P1) | Phase 2 complete | After T004-T006 |
| Phase 4 — US4 (P1) | Phase 3 complete (tools must be in canonical location before factories reference them) | After T018 passes |
| Phase 5 — US2 (P2) | Phase 4 complete (non-orchestrating agent factories must exist before PluginManager refactor loads them); also includes T022+T024 (micromanager) which require `shared["_registry"]` wired in T028 | After T025 passes |
| Phase 6 — US3 (P3) | Phase 5 complete (manifest loader must be wired into PluginManager) | After T030 passes |
| Phase 7 — Polish | Phase 6 complete | After T038 passes |

### User Story Dependencies

- **US1 (P1)**: Depends only on Foundational phase — no other user story dependency
- **US4 (P1, partial)**: Depends on US1 — core agent factories (Coder, Architect, Ask) reference tools from `core/tools/` canonical location; micromanager factory (T022) and manifest (T024) are deferred to Phase 5
- **US2 (P2)**: Depends on US4 — `PluginManager` refactor loads agent factories; includes micromanager migration (T022+T024) since micromanager requires `shared["_registry"]` populated in T028
- **US3 (P3)**: Depends on US2 — manifest loader must be wired into `PluginManager` before remaining plugins are migrated

### Within Each Phase

- Tasks marked `[P]` within the same phase can be executed concurrently (they touch different files)
- Non-`[P]` tasks within a phase must complete before the next task begins
- Each `pytest` run at a phase checkpoint is a hard gate — must pass before the next phase starts

---

## Parallel Execution Examples

### Phase 2: Foundational (launch all three together)

```
Task T004: Create pocketcode/core/namespace_registry.py
Task T005: Create pocketcode/core/manifest_loader.py
Task T006: Update pocketcode/core/runtime_models.py
```

### Phase 3 US1: Core Tool Files (launch T007–T011 together, then T012–T016 together)

```
# Batch 1 — copy implementations to canonical location:
Task T007: Copy filesystem.py → core/tools/filesystem.py
Task T008: Copy system.py → core/tools/system.py
Task T009: Copy git.py → core/tools/git.py
Task T010: Copy search.py → core/tools/search.py
Task T011: Copy user_input.py → core/tools/user_input.py

# Batch 2 — replace originals with wrappers (after Batch 1 complete):
Task T012: Replace pocketcode/tools/filesystem.py with re-export wrapper
Task T013: Replace pocketcode/tools/system.py with re-export wrapper
Task T014: Replace pocketcode/tools/git.py with re-export wrapper
Task T015: Replace pocketcode/tools/search.py with re-export wrapper
Task T016: Replace pocketcode/tools/user_input.py with re-export wrapper
```

### Phase 4 US4: Agent Factories (launch T019–T021 together)

```
Task T019: Create core/agents/coder_agent.py
Task T020: Create core/agents/architect_agent.py
Task T021: Create core/agents/ask_agent.py
```

### Phase 6 US3: Remaining Plugin Migration (launch T033–T037 together)

```
Task T033: Create arkitekt/agents/arkitekt_agent.py
Task T034: Convert arkitekt/agent.yaml → plugin.yaml
Task T035: Create asker/agents/asker_agent.py
Task T036: Convert asker/agent.yaml → plugin.yaml
Task T037: Write tests/unit/test_manifest_loader.py
```

---

## Implementation Strategy

### MVP First (US1 + US4 Only — both P1)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (new modules created)
3. Complete Phase 3: US1 — tools in canonical location; wrappers in place
4. Complete Phase 4: US4 — all existing agents have PocketFlow factories; no regressions
5. **STOP and VALIDATE**: All existing integration tests pass. Core plugin fully self-contained. Ship if needed.

### Incremental Delivery

1. Setup + Foundational → Pure additions, zero risk
2. US1 (Phase 3) → Tool relocation; backward compat wrappers make it invisible to callers
3. US4 (Phase 4) → Agent factories; existing agents work via new code paths
4. US2 (Phase 5) → `PluginManager` refactor; `NamespaceRegistry` live; qualified names work
5. US3 (Phase 6) → Last `agent.yaml` files migrated; clean startup with no legacy warnings

### Risk Mitigation

| Risk | Mitigation |
|---|---|
| Import breakage after tool move | Re-export wrappers preserve all public symbols; integration tests validate in T018 |
| Agent behavior regression during Flow port | Existing integration tests are the gate; pass at T025 before touching PluginManager |
| `PluginManager` refactor breaks session lookup | Unit tests in T029 validate all resolution paths before wiring into live system |
| `execute_shell_command` missing after tool move | T013 explicitly re-exports it; validated by `python -c` smoke test in T018 checkpoint |

---

## Task Summary

| Phase | Tasks | User Story | Priority |
|---|---|---|---|
| Phase 1: Setup | T001–T003 | — | — |
| Phase 2: Foundational | T004–T006 | — | — |
| Phase 3 | T007–T016 + T011a + T011b | US1 | P1 |
| Phase 4 | T019–T021, T023, T025 | US4 (partial) | P1 |
| Phase 5 | T022, T024, T026–T030 | US4 (micromanager) + US2 | P1+P2 |
| Phase 6 | T031–T038 | US3 | P3 |
| Phase 7: Polish | T039–T043 | — | — |
| **Total** | **45 tasks** | 4 user stories | — |

### Parallel Opportunities Identified

- Phase 2: 3 tasks in parallel (T004, T005, T006)
- Phase 3: 5+5 tasks in two parallel batches (T007–T011, then T012–T016)
- Phase 4: 3 tasks in parallel (T019, T020, T021)
- Phase 5: 2 tasks in parallel (T027, T029)
- Phase 6: 5 tasks in parallel (T033, T034, T035, T036, T037)
- Phase 7: 4 tasks in parallel (T039, T040, T041, T042)
