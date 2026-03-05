# Tasks: PocketFlow Agents and Plugin Factory

**Input**: Design documents from `/specs/002-pocketflow-agents/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are explicitly requested in the specification for User Story 1, 2, and 3 to ensure independent functional verification.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- All descriptions include exact file paths

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create project structure for feature 002 per implementation plan
- [X] T002 [P] Update `.github/agents/copilot-instructions.md` with PocketFlow factory patterns

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

- [X] T003 Implement `Plugin` dataclass in `pocketcode/core/interfaces.py`
- [X] T004 Implement `PluginContext` class in `pocketcode/core/interfaces.py`
- [X] T005 Create `PocketFlowAgent` wrapper in `pocketcode/core/runtime_nodes.py` to bridge `AgentDefinition` and `pocketflow.Flow`
- [X] T006 Update `AgentDefinition` in `pocketcode/core/runtime_models.py` to include `flow_instance` and `is_programmatic` flag
- [X] T007 [P] Create helper `get_plugin_context(shared)` in `pocketcode/core/interfaces.py` for node-level access

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Create and Run a PocketFlow Agent (Priority: P1) 🎯 MVP

**Goal**: Define agent logic directly using PocketFlow's Node and Flow classes.

**Independent Test**: Create a standalone plugin with a PocketFlow agent and run it via CLI to verify execution.

### Tests for User Story 1

- [X] T008 [P] [US1] Create integration test in `tests/integration/test_pocketflow_agent_execution.py` (Verify Flow node sequence)
- [X] T009 [P] [US1] Create integration test in `tests/integration/test_pocketflow_conditional_branching.py` (Verify action-based transitions)
- [X] T010 [US1] Update `AgentRuntime._run_agent_turn` in `pocketcode/core/agent_runtime.py` to detect and execute `pocketflow.Flow`
- [X] T011 [US1] Implement flow execution logic in `AgentRuntime._run_pocketflow_agent` in `pocketcode/core/agent_runtime.py`
- [X] T012 [US1] Implement `PluginContext` injection into `shared` store within `AgentRuntime` before flow execution
- [X] T028 [US1] Sub-task for T011: Implement state mapping between `pocketflow.Flow` results and `AgentRuntime` transitions (Action Mapping)

---

## Phase 4: User Story 2 - Plugin Factory Registration (Priority: P1)

**Goal**: Clean, centralized registration via `get_plugin()` factory function.

**Independent Test**: Verify `PluginManager` discovers tools/agents from a factory-based plugin.

### Tests for User Story 2

- [X] T013 [P] [US2] Create integration test in `tests/integration/test_factory_plugin_discovery.py` (Verify tool/agent registration)
- [X] T014 [P] [US2] Create mock factory plugin for testing discovery logic
- [X] T015 [US2] Implement global tool registration from `Plugin.tools` in `PluginManager._load_factory_plugin`
- [X] T016 [US2] Implement global agent registration from `Plugin.agents` in `PluginManager._load_factory_plugin`
- [X] T017 [US2] Update `template` plugin to use `get_plugin()` factory to provide a `PocketFlowAgent`
- [X] T018 [US2] Add integration test for end-to-end execution of a factory-delivered PocketFlow agent

---

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all story phases.
- **User Stories (Phase 3-5)**: All depend on Foundational completion.
- **Polish (Phase 6)**: Depends on all user stories being complete.

### User Story Dependencies

- **User Story 1 & 2**: Both are P1 and can run in parallel if the Foundational classes (`Plugin`, `PluginContext`, `PocketFlowAgent`) are ready.
- **User Story 3**: Depends on User Story 1 (Execution context) and User Story 2 (Registration).

### Parallel Opportunities

- T002, T007 are parallelizable setup/foundational tasks.
- T008, T009 (tests for US1) can be written in parallel.
- T013, T014 (tests for US2) can be written in parallel.
- T015, T016 are completed implementation tasks for story 2.
- Integration tests can be developed while implementation is in progress.

---

## Implementation Strategy

### MVP First (User Story 1 & 2)

1. Complete Foundational (Phase 2).
2. Complete US1 Implementation (T010-T012).
3. Complete US2 Implementation (T015-T018).
4. Run integration test combining factory registration with flow execution.

### Incremental Delivery

1. Foundation ready.
2. Programmatic flow execution ready (US1).
3. Unified factory registration ready (US2).
4. Local prompt/tool access refined (US3).
5. All legacy agents continue to work alongside new flows (Backward Compatibility).

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label for traceability.
- Backward compatibility is maintained by the fallback logic in `PluginManager`.
- Each story is verified by independent integration tests.
