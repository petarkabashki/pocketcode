---

description: "Task list for 006-session-history-controls"

---

# Tasks: Session History Controls

**Input**: Design documents from `/specs/006-session-history-controls/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/session-history-cli.md ✅, contracts/tool-approval-interactions.md ✅, quickstart.md ✅

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.
**Tests**: Test tasks are included because the spec and quickstart explicitly require validation of scoped approval behavior, session lifecycle behavior, and destructive-session safeguards.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (`US1`, `US2`, `US3`)
- Exact file paths are included in every task description

---

## Phase 1: Setup (Shared Session Feature Scaffold)

**Purpose**: Create the new landing zones and test scaffolds needed by the feature.

- [X] T001 Create the workspace-scoped session persistence module scaffold in pocketcode/core/session_manager.py
- [X] T002 [P] Add saved-session test scaffolding in tests/unit/test_session_manager.py
- [X] T003 [P] Add scoped-approval test scaffolding in tests/unit/test_tool_runtime.py

**Checkpoint**: New source and test landing zones exist for session persistence and scoped approval work.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the shared persistence and interaction infrastructure that all user stories depend on.

**⚠️ CRITICAL**: No user story work should begin until this phase is complete.

- [X] T004 Implement saved-session record serialization, transcript entry serialization, and storage-path helpers in pocketcode/core/session_manager.py
- [X] T005 Implement file-backed create, load, list, update, delete, and clear helper methods in pocketcode/core/session_manager.py
- [X] T006 Extend engine initialization and status state to track an active saved session in pocketcode/core/engine.py
- [X] T007 Extend pocketcode/core/engine.py request lifecycle hooks to attach session ids to shared_store and persist transcript snapshots on run completion
- [X] T008 [P] Extend structured interaction parsing and option rendering for explicit button values in pocketcode/cli/user_interaction.py
- [X] T009 [P] Add session lifecycle and scoped approval runtime event formatting in pocketcode/cli/runtime_events.py

**Checkpoint**: Shared session persistence, engine lifecycle hooks, and cross-interface interaction primitives are ready for story implementation.

---

## Phase 3: User Story 1 - Scoped Tool Permission Choices (Priority: P1) 🎯 MVP

**Goal**: Let a user approve a specific tool once, for the current session, or persistently across sessions.

**Independent Test**: Trigger a tool confirmation prompt, choose `once`, `session`, and `always` in turn, and verify the next request for the same tool follows the expected lifetime without granting access to other tools.

### Tests for User Story 1

- [X] T010 [P] [US1] Add scoped approval option parsing assertions in tests/unit/test_cli_user_interaction.py
- [X] T011 [P] [US1] Add once/session/always tool confirmation behavior tests in tests/unit/test_tool_runtime.py
- [X] T012 [P] [US1] Add scoped approval lifecycle coverage in tests/unit/test_engine_runtime_events.py
- [X] T013 [P] [US1] Add Textual approval interaction coverage in tests/unit/test_textual_app.py

### Implementation for User Story 1

- [X] T014 [US1] Update confirmation request construction and normalized scoped-response handling in pocketcode/plugins/core/tools/user_input.py
- [X] T015 [US1] Implement once/session/always decision handling and fail-closed approval behavior in pocketcode/core/tool_runtime.py
- [X] T016 [US1] Add engine helpers for persistent tool approval updates and session confirmation replacement in pocketcode/core/engine.py
- [X] T017 [US1] Update Textual approval interaction handling for scoped button choices in pocketcode/cli/textual_ui/interaction_mixin.py

**Checkpoint**: Scoped tool approval behavior is independently functional across CLI and Textual interfaces.

---

## Phase 4: User Story 2 - Resume or Start Sessions Intentionally (Priority: P1)

**Goal**: Let a user start a new session, keep previous sessions, list saved sessions with title and timestamp, and resume a selected session with its context restored.

**Independent Test**: Create multiple sessions, confirm previous sessions remain in history, then resume a prior session and verify that the conversation context and session-scoped confirmation state are restored.

### Tests for User Story 2

- [X] T018 [P] [US2] Add create/list/load session persistence coverage in tests/unit/test_session_manager.py
- [X] T019 [P] [US2] Add `/session show|list|new|resume` command contract coverage in tests/unit/test_command_handler.py
- [X] T020 [P] [US2] Add Textual session-history list and resume coverage in tests/unit/test_textual_app.py

### Implementation for User Story 2

- [X] T021 [US2] Implement autogenerated session title generation and readable session list projections in pocketcode/core/session_manager.py
- [X] T022 [US2] Implement engine session creation and resume flows that restore agent, mode, skills, LLM selection, and session overrides in pocketcode/core/engine.py
- [X] T023 [US2] Implement `/session show|list|new|resume` handlers in pocketcode/cli/command_handler.py
- [X] T024 [US2] Implement Textual session-history actions backed by engine session methods in pocketcode/cli/textual_ui/control_center_mixin.py
- [X] T025 [US2] Update active-session display and session-history UI state in pocketcode/cli/textual_ui/base.py

**Checkpoint**: Users can intentionally start fresh work or resume prior workspace sessions without losing prior history.

---

## Phase 5: User Story 3 - Remove Session History Safely (Priority: P2)

**Goal**: Let a user delete one previous session or clear all previous sessions with explicit confirmation while protecting the active session and leaving persistent approvals untouched.

**Independent Test**: Delete one non-active session and confirm only that session disappears, then clear all remaining previous sessions after confirmation and verify the active session still exists.

### Tests for User Story 3

- [X] T026 [P] [US3] Add session delete and clear-all persistence safeguards in tests/unit/test_session_manager.py
- [X] T027 [P] [US3] Add `/session delete|clear-all` confirmation and active-session protection coverage in tests/unit/test_command_handler.py
- [X] T028 [P] [US3] Add Textual delete and clear-all safeguard coverage in tests/unit/test_textual_app.py

### Implementation for User Story 3

- [X] T029 [US3] Implement engine delete and clear-all session APIs with active-session guards and unreadable-session handling in pocketcode/core/engine.py
- [X] T030 [US3] Implement `/session delete|clear-all` handlers with explicit confirmation in pocketcode/cli/command_handler.py
- [X] T031 [US3] Implement Textual delete and clear-all session actions with confirmation flows in pocketcode/cli/textual_ui/control_center_mixin.py

**Checkpoint**: Session history cleanup is independently functional and safe against destructive mistakes.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Align docs and validation with the completed runtime behavior across all stories.

- [X] T032 [P] Update session lifecycle and persistence documentation in docs/architecture.md and docs/configuration.md
- [X] T033 [P] Update command and interaction documentation in docs/cli.md
- [X] T034 Run the quickstart validation steps in specs/006-session-history-controls/quickstart.md
- [X] T035 Run the focused session-history and approval unit suite in tests/unit/test_session_manager.py tests/unit/test_tool_runtime.py tests/unit/test_engine_runtime_events.py tests/unit/test_command_handler.py tests/unit/test_cli_user_interaction.py tests/unit/test_textual_app.py

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion; blocks all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational completion
- **User Story 2 (Phase 4)**: Depends on Foundational completion
- **User Story 3 (Phase 5)**: Depends on Foundational completion and should follow the session create/list/resume work from User Story 2 for the same command/UI files
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2 and delivers the approval-scope MVP
- **User Story 2 (P1)**: Can start after Phase 2 and delivers the saved-session MVP for starting and resuming work
- **User Story 3 (P2)**: Depends on the saved-session infrastructure from Phase 2 and shares command/UI files with User Story 2, so sequence edits to pocketcode/cli/command_handler.py and pocketcode/cli/textual_ui/control_center_mixin.py carefully

### Within Each User Story

- Test tasks should be written before their implementation tasks and should fail before implementation is considered complete
- For User Story 1, update the confirmation tool response contract before finalizing tool runtime policy handling and Textual interaction behavior
- For User Story 2, finish session title/list projection and engine restore logic before finalizing CLI and Textual resume surfaces
- For User Story 3, add destructive-action test coverage before implementing delete and clear-all flows in engine, CLI, and Textual surfaces

### Parallel Opportunities

- T002 and T003 can run in parallel
- T008 and T009 can run in parallel after T006 and T007 are understood
- T010, T011, T012, and T013 can run in parallel
- T018, T019, and T020 can run in parallel
- T026, T027, and T028 can run in parallel
- T032 and T033 can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch scoped approval verification work together:
Task: "Add scoped approval option parsing assertions in tests/unit/test_cli_user_interaction.py"
Task: "Add once/session/always tool confirmation behavior tests in tests/unit/test_tool_runtime.py"
Task: "Add Textual approval interaction coverage in tests/unit/test_textual_app.py"

# After tests exist, split implementation safely:
Task: "Update confirmation request construction and normalized scoped-response handling in pocketcode/plugins/core/tools/user_input.py"
Task: "Update Textual approval interaction handling for scoped button choices in pocketcode/cli/textual_ui/interaction_mixin.py"
```

---

## Parallel Example: User Story 2

```bash
# Build session lifecycle coverage together:
Task: "Add create/list/load session persistence coverage in tests/unit/test_session_manager.py"
Task: "Add `/session show|list|new|resume` command contract coverage in tests/unit/test_command_handler.py"
Task: "Add Textual session-history list and resume coverage in tests/unit/test_textual_app.py"
```

---

## Parallel Example: User Story 3

```bash
# Verify destructive safeguards together:
Task: "Add session delete and clear-all persistence safeguards in tests/unit/test_session_manager.py"
Task: "Add `/session delete|clear-all` confirmation and active-session protection coverage in tests/unit/test_command_handler.py"
Task: "Add Textual delete and clear-all safeguard coverage in tests/unit/test_textual_app.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 + User Story 2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. Complete Phase 4: User Story 2
5. **STOP and VALIDATE**: Confirm scoped approvals and session start/resume behavior work independently before moving to deletion flows

### Incremental Delivery

1. Finish Setup + Foundational to establish session persistence and shared interaction plumbing
2. Deliver User Story 1 to make tool approval durations explicit and correct
3. Deliver User Story 2 to enable starting, listing, and resuming sessions
4. Deliver User Story 3 to add safe history cleanup
5. Finish docs and validation in Phase 6

### Parallel Team Strategy

With multiple developers:

1. One developer owns session persistence and engine lifecycle work in pocketcode/core/session_manager.py and pocketcode/core/engine.py
2. One developer owns approval interaction and tool runtime work in pocketcode/plugins/core/tools/user_input.py, pocketcode/core/tool_runtime.py, and pocketcode/cli/user_interaction.py
3. One developer owns shared command and Textual session surfaces in pocketcode/cli/command_handler.py and pocketcode/cli/textual_ui/

---

## Notes

- [P] tasks touch different files and avoid dependencies on incomplete work in the same file
- `pocketcode/core/session_manager.py` and `tests/unit/test_session_manager.py` are new files expected for this feature
- Saved session state is workspace-local and must remain distinct from persistent `runtime.tool_confirmation` settings
- Documentation updates are required by the repo instructions and are included explicitly in Phase 6