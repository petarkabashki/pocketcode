# Tasks: Refactor Plugin Structure and Composition

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Implementation Strategy
Minimalist refactor using `pocketflow.py` as the core. Transition from hardcoded logic in `mode_flows/` to user-supplied agent folders in `pocketcode/plugins/`.

---

## Phase 1: Setup & Contracts
Initialize new folder structures and define the agent manifest schema.

- [X] T001 Create directory structure for user-supplied agents in `pocketcode/plugins/`
- [X] T002 Define JSON schema for `agent.yaml` in `specs/001-refactor-plugin-structure/contracts/agent-schema.json`
- [X] T003 [P] Create base `agent.yaml` template in `pocketcode/plugins/template/agent.yaml`

---

## Phase 2: Foundational Orchestration (Minimalist PocketFlow)
Refactor the generic runtime to be a thin layer over `pocketflow.py`.

- [X] T004 Refactor `pocketcode/core/workflow_runtime.py` to use `pocketflow.Flow` and `pocketflow.Node` directly
- [X] T005 Implement `PluginManager` update to scan `pocketcode/plugins/` for `agent.yaml` manifests
- [X] T006 [P] Update `ToolRuntime` to search for tools in both local plugin `tools/` and global `pocketcode/tools/`
- [X] T007 Implement minimalist `BaseAgentNode` in `pocketcode/core/runtime_nodes.py` that maps `pocketflow.Node.prep` and `post`

---

## Phase 3: User Story 1 - User-Supplied Agent Plugins (Priority: P1) 🎯 MVP
**Goal**: Enable loading of self-contained agent personas and assets.

**Independent Test**: Verify agent loading via CLI with a test dummy agent folder.

- [ ] T008 [US1] Create `architect` agent plugin in `pocketcode/plugins/architect/` (moving existing assets)
- [ ] T009 [US1] Create `coder` agent plugin in `pocketcode/plugins/coder/`
- [ ] T010 [US1] Implement persona loading logic in `pocketcode/core/prompt_loader.py` to resolve local `prompts/`
- [ ] T011 [P] [US1] Verify agent loading via CLI with a test dummy agent folder

---

## Phase 4: User Story 2 - Minimal PocketFlow Orchestration (Priority: P1)
**Goal**: Ensure multi-agent loops and recursion use native `pocketflow` patterns.

**Independent Test**: Execute the "orchestrator" workflow and verify it uses `pocketflow.Flow` and `pocketflow.Node` for execution transitions.

- [ ] T012 [US2] Map `handoff` action to `pocketflow` node transitions
- [ ] T013 [US2] Implement recursive flow delegation using `pocketflow.Flow` as a node in `WorkflowRuntime`
- [ ] T014 [P] [US2] Create integration test for a multi-agent loop using `pocketflow` native transitions

---

## Phase 5: Removal of Obsolete Implementations (Priority: P2)
**Goal**: Cleanup legacy hardcoded flows.

**Independent Test**: Verify that `pocketcode/mode_flows/` is removed and agents run via plugins.

- [ ] T015 Remove `pocketcode/mode_flows/asker.py` and migrate to `asker` agent plugin
- [ ] T016 Remove `pocketcode/mode_flows/micromanager.py` and migrate to `micromanager` agent plugin
- [ ] T017 Delete entire `pocketcode/mode_flows/` directory
- [ ] T018 Remove redundant plugin asset folders from `pocketcode/plugins/core/` (after migration)

---

## Final Phase: Polish & Validation
Ensure everything is self-contained and minimalist.

- [ ] T019 Update `readme.md` to document the new user-supplied agent framework
- [ ] T020 Run full suite of integrated tests for all migrated agents
- [ ] T021 [P] [US1] Performance test: Verify plugin loading overhead is < 100ms

---

## Dependencies & Execution Order

- **Phase 1 (Setup)**: No dependencies.
- **Phase 2 (Foundational)**: Depends on Phase 1 completion - BLOCKS all user stories.
- **Phase 3 (User Story 1)**: Depends on Phase 2 completion.
- **Phase 4 (User Story 2)**: Depends on Phase 3 (Asset Loading) completion.
- **Phase 5 (Cleanup)**: MUST happen after Phase 3 and Phase 4 are verified.

## Parallel Execution Examples
- T003, T006, T011 can run in parallel (asset templates and tool lookup)
- T002 and T005 can run in parallel (contract definition vs manager logic)
