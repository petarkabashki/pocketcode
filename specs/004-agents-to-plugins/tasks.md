---

description: "Task list for 004-agents-to-plugins"
---

# Tasks: Agents to Plugins — Core ReAct Agent Only

**Input**: Design documents from `/specs/004-agents-to-plugins/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/plugin-agent-manifest.md ✅, quickstart.md ✅

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.
**Tests**: No TDD test tasks generated — spec requests existing tests be updated (FR-009), not written before implementation.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths included in every description

---

## Phase 1: Setup (Cleanup)

**Purpose**: Remove stale artifacts before any changes to avoid confusing __pycache__ entries.

- [x] T001 [P] Remove stale __pycache__ artifacts from pocketcode/plugins/core/agents/; verify that coder_agent.py exists in .pocketcode/plugins/coder/agents/, architect_agent.py in .pocketcode/plugins/architect/agents/, and asker_agent.py in .pocketcode/plugins/asker/agents/ (FR-006 precondition — research §1 confirms they are already there, but this check makes the assumption explicit)

**Checkpoint**: Core agents directory is clean; domain agent .py files confirmed in correct locations — ready for new react_agent.py.

---

## Phase 2: Foundational (Blocking Prerequisite)

**Purpose**: Update the top-level runtime config. This must be done before US1 or US2 are tested, since the default agent and workflow key affect every agent invocation.

**⚠️ CRITICAL**: Core plugin and domain plugin work in Phases 3/4 depend on this config being correct.

- [x] T002 Update pocketcode.yml — set `runtime.default_agent: core::react`; remove `runtime.agent_runtime_workflow` key entirely (research §7 + quickstart smoke test)

**Checkpoint**: Config updated — agent invocation will resolve to `core::react` by default.

---

## Phase 3: User Story 1 — Core plugin: single ReAct agent (Priority: P1) 🎯 MVP

**Goal**: `core/plugin.yaml` declares exactly one agent (`react`). The `single_agent` flow and its prompts are removed. A purpose-built ReAct loop is implemented in `core/agents/react_agent.py`.

**Independent Test**:
```bash
python - <<'EOF'
import yaml
with open("pocketcode/plugins/core/plugin.yaml") as f:
    data = yaml.safe_load(f)
agents = list(data.get("agents", {}).keys())
assert agents == ["react"], f"Expected ['react'], got {agents}"
print("✅ Story 1 manifest check passed")
EOF
```

### Implementation for User Story 1

- [x] T003 [P] [US1] Delete pocketcode/plugins/core/prompts/flows/single_agent.md (FR-013)
- [x] T004 [P] [US1] Delete pocketcode/plugins/core/prompts/nodes/single_agent/ directory and all contents (FR-013, SC-007)
- [x] T005 [US1] Create pocketcode/plugins/core/agents/react_agent.py — implement `create_flow()` returning a pocketflow `Flow` composed of `ReasonNode` → `ActNode` → `ObserveNode` → `FinalNode`; store trace in `react_trace`, guard with `react_step_count ≤ max_agent_steps` (data-model §4, research §5, FR-012)
- [x] T006 [US1] Update pocketcode/plugins/core/plugin.yaml — remove `coder`, `architect`, and `ask` agent entries; add `react` agent entry per the canonical schema in `contracts/plugin-agent-manifest.md` (module: agents/react_agent.py, entry_fn: create_flow, llm_profile: gemini_default, full core tool list) (FR-001, FR-002, SC-001)

**Checkpoint**: `core` plugin loads, `core::react` is the only registered agent, single_agent files are absent. Verify with quickstart Story 1 scripts.

---

## Phase 4: User Story 2 — Domain agents in their own plugins (Priority: P1)

**Goal**: `coder::coder`, `architect::architect`, and `asker::ask` are each fully registered in their own plugin manifests with correct tool bindings and fully-qualified handoff references. No cross-plugin file references.

**Independent Test**:
```bash
python - <<'EOF'
import yaml
checks = [
    (".pocketcode/plugins/coder/plugin.yaml",     "coder",     "coder"),
    (".pocketcode/plugins/architect/plugin.yaml", "architect", "architect"),
    (".pocketcode/plugins/asker/plugin.yaml",     "asker",     "ask"),
]
for path, name, agent in checks:
    with open(path) as f:
        data = yaml.safe_load(f)
    assert data["name"] == name
    assert agent in data.get("agents", {})
    print(f"✅ {name}::{agent}")
EOF
```

### Implementation for User Story 2

- [x] T007 [P] [US2] Update .pocketcode/plugins/coder/plugin.yaml — rename agent key `coder` → `coder`; add full tool list (local: write_to_file, create_directory, git_diff; cross-plugin: core::read_file, core::list_files, core::glob_files, core::search_code, core::execute_command, core::git_status, core::git_add, core::git_commit, core::git_pull, core::git_push); set handoff_agents: [architect::architect, asker::ask] (FR-003, research §2, contract coder section)
- [x] T008 [P] [US2] Update .pocketcode/plugins/architect/plugin.yaml — confirm agent key is `architect`; add core::glob_files to tools; set handoff_agents: [coder::coder, asker::ask] in fully-qualified form (FR-004, research §3, contract architect section)
- [x] T009 [P] [US2] Update .pocketcode/plugins/asker/plugin.yaml — rename plugin `name` field from `ask` to `asker`; confirm agent key is `ask`; expand tools with core::read_file, core::list_files, core::glob_files, core::search_code; set handoff_agents: [coder::coder, architect::architect] in fully-qualified form (FR-005, research §4, contract asker section)

**Checkpoint**: All three domain plugins register their agents. Run quickstart Story 2 manifest check script.

---

## Phase 5: User Story 3 — Handoff routing across plugin boundaries (Priority: P2)

**Goal**: All handoff references across the entire codebase use the fully-qualified `plugin::agent` form. `micromanager` is updated, integration tests reflect the new namespaces, and runtime handoff resolution works end-to-end.

**Independent Test**:
```bash
python - <<'EOF'
import yaml
with open(".pocketcode/plugins/coder/plugin.yaml") as f:
    data = yaml.safe_load(f)
handoffs = data["agents"]["coder"].get("handoff_agents", [])
for h in handoffs:
    assert "::" in h, f"Bare handoff '{h}' not allowed"
print("✅ Story 3 handoff format check passed")
EOF
```

### Implementation for User Story 3

- [x] T010 [US3] Update .pocketcode/plugins/micromanager/plugin.yaml — replace stale dot-notation references (`core.coder`, `core.architect`, `core.ask`) with fully-qualified form: `coder::coder`, `architect::architect`, `asker::ask` in handoff_agents (FR-007, FR-008, research §6, data-model Removal Checklist)
- [x] T011 [US3] Update tests/integration/test_pocketflow_plugin_discovery.py — replace any assertions on `core::coder`, `core::architect`, `core::ask` with the new namespaces `coder::coder`, `architect::architect`, `asker::ask`; extend tests/integration/test_pocketflow_agent_execution.py to assert the SC-004 full round-trip handoff sequence `coder::coder` → `architect::architect` → `coder::coder` completes without error (FR-009 partial, SC-004, research §8)

**Checkpoint**: Handoff format validation passes. Run quickstart Story 3 handoff check and `pytest tests/integration/test_pocketflow_agent_execution.py -v`.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, unit test alignment, and cleanup confirmation.

- [x] T012 [P] Update tests/unit/test_manifest_loader.py if it asserts agent names or plugin names that have changed (coder→coder agent key, ask→asker plugin name) (FR-009 partial)
- [x] T013 [P] Run quickstart.md filesystem verification checklist — confirm react_agent.py present, single_agent files absent, domain agent modules in place; run a timed `core::react` smoke invocation and assert wall-clock < 5 s (SC-005; warm = Python interpreter already initialized, all manifests parsed)
- [x] T015 [P] Verify plugin isolation — run PocketCoder startup with only core + coder enabled; assert architect and asker agents are absent from the registry but no cascading failure or import error occurs; repeat for core + architect only, and core + asker only (FR-010, SC-006)
- [x] T014 Run full test suite — `pytest tests/ -v --tb=short` — verify zero regressions across all unit and integration tests; **FR-009 gate**: FR-009 is only fully satisfied when this task passes with 0 failures (T011/T012 provide per-story partial coverage) (FR-009 gate, SC-003)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: No dependencies — can run alongside Phase 1
- **User Story 1 (Phase 3)**: Depends on Phase 1 cleanup; config in Phase 2 should be done before testing
- **User Story 2 (Phase 4)**: Independent of US1 — can run in parallel with Phase 3
- **User Story 3 (Phase 5)**: Depends on US1 (Phase 3) and US2 (Phase 4) completion; all agents must be registered before handoff validation
- **Polish (Phase 6)**: Depends on all story phases complete

### User Story Dependencies

- **US1 (P1)**: Independent — only touches `core/` files
- **US2 (P1)**: Independent — only touches `coder/`, `architect/`, `asker/` files
- **US3 (P2)**: Depends on US1 + US2 — requires all agents registered for handoff resolution

### Within Each User Story

- T003 and T004 (deletions) can run in parallel — different paths
- T005 (react_agent.py) should be created before T006 (manifest) so the module path can be verified
- T007, T008, T009 are all parallel — different plugin directories
- T010 (micromanager update) must come after T007/T008/T009 so target agents exist
- T015 (plugin isolation check) must come after T007/T008/T009 so plugins are wired before isolation is tested
- T014 (full test suite gate) must be the final task — it is the FR-009 gate

### Parallel Opportunities

```bash
# Phase 1 + Phase 2 in parallel:
Task T001: Remove core/agents/__pycache__
Task T002: Update pocketcode.yml

# Phase 3 + Phase 4 in parallel (different dirs):
Task T003: Delete single_agent.md
Task T004: Delete single_agent/ node dir
Task T007: Update coder/plugin.yaml
Task T008: Update architect/plugin.yaml
Task T009: Update asker/plugin.yaml

# After T003/T004 complete:
Task T005: Create react_agent.py
Task T006: Update core/plugin.yaml

# Phase 6 in parallel after all stories (before T014 gate):
Task T012: Update unit tests
Task T013: Run quickstart verification + SC-005 timing
Task T015: Plugin isolation check
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Cleanup (T001)
2. Complete Phase 2: Config (T002)
3. Complete Phase 3: US1 (T003 → T004 → T005 → T006)
4. **STOP and VALIDATE**: Run quickstart Story 1 checks independently
5. Proceed to US2 + US3

### Incremental Delivery

1. Setup + Foundational → config ready
2. US1 → core plugin clean, react agent functional — **independently testable**
3. US2 → domain plugins populated — **independently testable per plugin**
4. US3 → handoff routing complete, tests updated — **full system testable**
5. Polish → zero regressions confirmed

### Parallel Opportunities Summary

- T001 ∥ T002 (different targets)
- T003 ∥ T004 ∥ T007 ∥ T008 ∥ T009 (all different files/dirs)
- T012 ∥ T013 (different files)

---

## Notes

- No new plugin directories are created (plan.md Assumptions)
- No Python agent module files need to be moved — research §1 confirms `core/agents/` already has no .py source files
- The `coder_agent.py` filename stays as-is; only the manifest key changes (research §2)
- All handoff references must use `plugin::agent` form — bare short names are forbidden after this migration (FR-007)
- SC-005 performance target: `core::react` completes a tool call in < 5 s on a warm system — verified by T013 timed smoke invocation (warm = Python interpreter initialized, manifests parsed); avoid unnecessary startup overhead in react_agent.py
- Stale reference detection (descriptive error on startup) is enforced by the existing `NamespaceRegistry` validation from spec 003 — no new validation code required; it will fire automatically once the old agents are removed from `core/plugin.yaml`
