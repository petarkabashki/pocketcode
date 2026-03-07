---

description: "Task list for 005-cleanup-cli-consistency"

---

# Tasks: CLI Consistency Cleanup

**Input**: Design documents from `/specs/005-cleanup-cli-consistency/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/cli-command-surface.md ✅, quickstart.md ✅

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.
**Tests**: Test tasks are included because the spec explicitly requires automated verification of command availability, help/output behavior, and removal of stale compatibility surfaces.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (`US1`, `US2`, `US3`)
- Exact file paths are included in every task description

---

## Phase 1: Setup (Shared CLI Test Surface)

**Purpose**: Create the shared test entry points needed to verify the CLI contract across universal and interface-specific surfaces.

- [x] T001 [P] Create shared basic/one-shot CLI test scaffolding in tests/unit/test_main_cli.py
- [x] T002 [P] Extend shared command/help assertion scaffolding in tests/unit/test_command_handler.py

**Checkpoint**: Shared CLI contract test files exist and are ready for story-specific assertions.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the canonical command/help boundaries and remove the main structural blockers before any user story-specific cleanup.

**⚠️ CRITICAL**: No user story work should begin until this phase is complete.

- [x] T003 Refactor command metadata helpers in pocketcode/cli/command_handler.py to distinguish universal commands from interface-specific commands
- [x] T004 [P] Simplify startup and one-shot CLI entry handling in pocketcode/main.py so it no longer depends on workflow-era wording or deprecated routing assumptions
- [x] T005 [P] Simplify CLI-facing compatibility/status helpers in pocketcode/core/engine.py for the agent-centered public model
- [x] T006 [P] Remove obsolete completion aliases and unused CLI helper exports in pocketcode/cli/completers.py

**Checkpoint**: The command layer has a canonical universal surface, and the shared compatibility blockers are removed.

---

## Phase 3: User Story 1 - Reliable Command Surface (Priority: P1) 🎯 MVP

**Goal**: Ensure universal help, suggestions, and command routing expose only universally supported commands, while interface-specific commands remain discoverable only inside their owning interface.

**Independent Test**: Run the universal help and command contract tests, then verify `/help` and `/status` through one-shot CLI usage and confirm that interface-specific commands do not appear in universal help or shared suggestions.

### Tests for User Story 1

- [x] T007 [P] [US1] Add universal help, alias, and suggestion contract assertions in tests/unit/test_command_handler.py
- [x] T008 [P] [US1] Add one-shot and basic CLI command-surface assertions in tests/unit/test_main_cli.py
- [x] T009 [P] [US1] Add explicit interface-specific discovery coverage for Textual-only commands in tests/unit/test_main_cli.py or a new focused Textual CLI contract test file

### Implementation for User Story 1

- [x] T010 [US1] Update universal command listings, aliases, help text, and shared suggestion generation in pocketcode/cli/command_handler.py
- [x] T011 [US1] Update basic interactive CLI and one-shot command execution paths in pocketcode/main.py to return explicit interface-scope responses for non-universal commands
- [x] T012 [US1] Update Textual-only command interception and interface-local discovery in pocketcode/cli/textual_app.py so retained interface-specific commands remain local to Textual UI

**Checkpoint**: Universal command/help surfaces are trustworthy and independently testable without User Story 2 or User Story 3.

---

## Phase 4: User Story 2 - Clear Runtime Terminology (Priority: P2)

**Goal**: Make user-facing CLI wording consistently agent-centered and remove workflow terminology from startup output, status output, help text, and related documentation-facing command responses.

**Independent Test**: Run terminology-focused CLI tests, then verify that startup, `/help`, and `/status` output use agent-centered wording and contain no remaining workflow text.

### Tests for User Story 2

- [x] T013 [P] [US2] Add agent-centered wording assertions for help, status, and agent detail output in tests/unit/test_command_handler.py
- [x] T014 [P] [US2] Add startup and one-shot status terminology assertions in tests/unit/test_main_cli.py

### Implementation for User Story 2

- [x] T015 [US2] Replace workflow-era startup and one-shot CLI wording in pocketcode/main.py
- [x] T016 [US2] Replace workflow-era user-facing labels and status/help wording in pocketcode/cli/command_handler.py
- [x] T017 [US2] Remove workflow-facing status fields or CLI dependencies still surfaced through pocketcode/core/engine.py

**Checkpoint**: Agent-centered public terminology is consistent and independently testable across startup and command output.

---

## Phase 5: User Story 3 - Lower Maintenance Overhead (Priority: P3)

**Goal**: Remove obsolete internal compatibility helpers, deprecated routing adapters, and dead CLI leftovers tied to the old terminology and command model.

**Independent Test**: Run regression tests that assert removed compatibility routes, removed deprecated flags, and removed obsolete helper surfaces no longer exist while supported behavior continues to work.

### Tests for User Story 3

- [x] T018 [P] [US3] Add regression coverage for removed deprecated aliases and routing adapters in tests/unit/test_command_handler.py
- [x] T019 [P] [US3] Add regression coverage for removed deprecated entrypoint flags and startup compatibility paths in tests/unit/test_main_cli.py

### Implementation for User Story 3

- [x] T020 [US3] Remove deprecated aliases, obsolete routing adapters, and compatibility-only branches from pocketcode/cli/command_handler.py
- [x] T021 [US3] Remove deprecated CLI flags and obsolete compatibility paths from pocketcode/main.py
- [x] T022 [US3] Remove obsolete CLI-facing compatibility helpers tied only to old routing or terminology from pocketcode/core/engine.py
- [x] T023 [US3] Remove obsolete completion helpers and alias exports from pocketcode/cli/completers.py

**Checkpoint**: Deprecated compatibility layers are gone, and the command layer is simpler to maintain without hidden legacy routing surfaces.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Bring docs and validation into line with the cleaned contract across all stories.

- [x] T024 [P] Update CLI-facing documentation in readme.md and docs/README.md to match the cleaned universal command/help surface
- [x] T025 [P] Update docs/modes_and_skills.md and docs/pocketflow_agents.md to remove workflow-era CLI wording and describe interface-specific discovery correctly
- [x] T026 Run the validation steps in specs/005-cleanup-cli-consistency/quickstart.md and record any required follow-up fixes
- [x] T027 Run the focused CLI test suite in tests/unit/test_command_handler.py tests/unit/test_cli_user_interaction.py tests/unit/test_main_cli.py

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion; blocks all user story work
- **User Story 1 (Phase 3)**: Depends on Foundational completion
- **User Story 2 (Phase 4)**: Depends on Foundational completion; can proceed after US1 if the same files are in conflict, otherwise in parallel where safe
- **User Story 3 (Phase 5)**: Depends on Foundational completion and should follow US1/US2 updates for the files whose legacy helpers are being removed
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2 and delivers the MVP command/help contract
- **User Story 2 (P2)**: Can start after Phase 2 but overlaps file ownership with US1, so coordinate sequencing around pocketcode/main.py, pocketcode/cli/command_handler.py, and pocketcode/core/engine.py
- **User Story 3 (P3)**: Depends on the intended universal/interface-specific contract and terminology choices being implemented first so obsolete helpers can be removed safely

### Within Each User Story

- Test tasks should be written before the corresponding implementation tasks and should fail before the implementation is completed
- For US1, shared command/help behavior in pocketcode/cli/command_handler.py should be updated before the entrypoint and Textual-specific paths are finalized
- For US2, user-facing wording in pocketcode/main.py and pocketcode/cli/command_handler.py should be updated before removing remaining CLI-facing workflow dependencies from pocketcode/core/engine.py
- For US3, obsolete compatibility helpers should be removed only after the supported command/help model is already represented by US1 and US2 changes

### Parallel Opportunities

- T001 and T002 can run in parallel
- T004, T005, and T006 can run in parallel after T003 if file conflicts are avoided
- T007, T008, and T009 can run in parallel
- T013 and T014 can run in parallel
- T018 and T019 can run in parallel
- T024 and T025 can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch User Story 1 tests together:
Task: "Add universal help, alias, and suggestion contract assertions in tests/unit/test_command_handler.py"
Task: "Add one-shot and basic CLI command-surface assertions in tests/unit/test_main_cli.py"
Task: "Add explicit interface-specific discovery coverage for Textual-only commands in tests/unit/test_main_cli.py or a new focused Textual CLI contract test file"

# After tests exist, split interface-specific and universal implementation work:
Task: "Update universal command listings, aliases, help text, and shared suggestion generation in pocketcode/cli/command_handler.py"
Task: "Update Textual-only command interception and interface-local discovery in pocketcode/cli/textual_app.py so retained interface-specific commands remain local to Textual UI"
```

---

## Parallel Example: User Story 2

```bash
# Launch terminology verification together:
Task: "Add agent-centered wording assertions for help, status, and agent detail output in tests/unit/test_command_handler.py"
Task: "Add startup and one-shot status terminology assertions in tests/unit/test_main_cli.py"
```

---

## Parallel Example: User Story 3

```bash
# Launch cleanup regressions together:
Task: "Add regression coverage for removed deprecated aliases and routing adapters in tests/unit/test_command_handler.py"
Task: "Add regression coverage for removed deprecated entrypoint flags and startup compatibility paths in tests/unit/test_main_cli.py"

# After supported behavior is stable, remove legacy helpers in parallel where files do not overlap:
Task: "Remove obsolete CLI-facing compatibility helpers tied only to old routing or terminology from pocketcode/core/engine.py"
Task: "Remove obsolete completion helpers and alias exports from pocketcode/cli/completers.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run `/help`, `/status`, and the US1 test coverage independently
5. Demo the cleaned universal command/help surface before proceeding

### Incremental Delivery

1. Finish Setup + Foundational to establish the canonical command/help model
2. Deliver User Story 1 for the universal command surface
3. Deliver User Story 2 for agent-centered terminology and output consistency
4. Deliver User Story 3 for internal compatibility/helper removal
5. Finish with docs and validation in Phase 6

### Parallel Team Strategy

With multiple developers:

1. One developer handles shared command/help metadata in pocketcode/cli/command_handler.py
2. One developer handles entrypoint and startup/status behavior in pocketcode/main.py and tests/unit/test_main_cli.py
3. One developer handles Textual/discovery cleanup in pocketcode/cli/textual_app.py and docs updates once the universal surface is settled

---

## Notes

- [P] tasks touch different files and have no dependency on incomplete work in the same file
- `tests/unit/test_main_cli.py` is expected to be created by this feature to cover startup, one-shot help, and deprecated entrypoint behavior
- `tests/unit/test_cli_user_interaction.py` remains part of the validation suite even if it does not require major task-level changes
- This feature intentionally removes deprecated routing and terminology helpers rather than hiding them behind compatibility shims
- Documentation updates are required by the repo instructions and are included explicitly in the polish phase