# Implementation Plan: Session History Controls

**Branch**: `006-session-history-controls` | **Date**: 2026-03-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/006-session-history-controls/spec.md`

## Summary

Add two coordinated capabilities to the existing CLI runtime: scoped tool approvals that let the user approve a tool once, for the current session, or persistently across sessions, and workspace-scoped saved conversation sessions that can be started, listed, resumed, deleted, and cleared without affecting the active session. The implementation should reuse the shared engine request path, keep persistent approvals in existing tool confirmation config, store saved conversation state in workspace-local session files, and surface the feature through shared slash commands plus Textual UI affordances.

## Technical Context

**Language/Version**: Python 3.10+ (repo currently exercised on Python 3.12)  
**Primary Dependencies**: pocketflow, PyYAML, textual, python-dotenv, pytest  
**Storage**: Workspace-local file storage for saved sessions under `.pocketcode/state/sessions/`; existing `pocketcode.yml` `runtime.tool_confirmation` remains the persistent store for always approvals  
**Testing**: pytest (`tests/unit/`), with targeted engine, tool runtime, CLI interaction, command handler, and Textual UI coverage  
**Target Platform**: Linux terminal environment supporting one-shot CLI, basic interactive CLI, and Textual UI  
**Project Type**: Single-project Python CLI / plugin-driven agent runtime  
**Performance Goals**: No user-perceptible slowdown in normal request execution; session list/load/delete operations should remain effectively instantaneous for typical workspace usage (dozens to low hundreds of saved sessions)  
**Constraints**: Saved sessions are workspace-scoped only; the active session cannot be deleted; always approvals must stay independent from session history cleanup; the behavior must work through shared engine paths rather than Textual-only buffers; avoid introducing eager core imports that could recreate known import cycles  
**Scale/Scope**: `pocketcode/core/engine.py`, `pocketcode/core/tool_runtime.py`, a new focused session persistence module, shared CLI command handling, Textual interaction surfaces, runtime event formatting, documentation, and corresponding unit tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Minimalist Orchestration | ✅ PASS | The design adds one focused persistence component for saved sessions and reuses the existing engine, RunHandle, command handler, and interaction system instead of creating a parallel runtime. |
| II. User-Supplied Agent Plugins | ✅ PASS | No plugin manifest, plugin loading, or plugin packaging contract changes are required; the feature is workspace/runtime state only. |
| III. Shared Core Tools | ✅ PASS | Tool approval behavior remains centralized in the existing shared tool confirmation path and does not move tool logic into plugins or UI-only code. |
| IV. Independent Testability | ✅ PASS | Scoped approvals, session create/resume/list flows, and session deletion/clear-all flows can each be tested independently at unit and command-surface levels. |

**Gate result before Phase 0**: PASS — proceed to research.

**Gate result after Phase 1 design**: PASS — the design keeps orchestration minimal, preserves plugin boundaries, and splits the work into independently testable stories.

## Project Structure

### Documentation (this feature)

```text
specs/006-session-history-controls/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── session-history-cli.md
│   └── tool-approval-interactions.md
└── tasks.md
```

### Source Code (repository root)

```text
pocketcode/
├── main.py                                 # Startup interface selection and one-shot/basic CLI entry paths
├── cli/
│   ├── command_handler.py                  # Shared slash commands; add session management surface
│   ├── runtime_events.py                   # Event text for session lifecycle and approval prompts
│   ├── user_interaction.py                 # Shared parsing/rendering for multi-option approval choices
│   └── textual_ui/
│       ├── interaction_mixin.py            # Textual interaction routing for richer approval/session actions
│       ├── control_center_mixin.py         # Textual entry points for session history controls
│       ├── base.py                         # UI state that reflects active session and history actions
│       └── ...                             # Any focused session-picker or dialog module introduced by implementation
├── core/
│   ├── engine.py                           # Shared request lifecycle, active session state, persistence hooks
│   ├── run_handle.py                       # Interaction payload bridge used by CLI and Textual UI
│   ├── tool_runtime.py                     # Approval scope resolution and session-vs-persistent policy application
│   └── session_manager.py                  # New workspace-scoped saved session CRUD component
└── plugins/
    └── core/
        └── tools/
            └── user_input.py               # Confirmation request builder returning explicit approval scopes

docs/
├── architecture.md                         # Session lifecycle and runtime persistence boundary
├── cli.md                                  # `/session` contract and approval prompt behavior
└── configuration.md                        # Workspace state storage layout and persistent approval separation

tests/
└── unit/
    ├── test_command_handler.py             # `/session` command contract and destructive-action confirmation behavior
    ├── test_cli_user_interaction.py        # Shared multi-option approval parsing
    ├── test_engine_runtime_events.py       # Shared-store session lifecycle integration
    ├── test_textual_app.py                 # Textual picker/dialog/session state behavior
    ├── test_tool_runtime.py                # Once/session/always approval semantics
    └── test_session_manager.py             # New saved-session persistence coverage
```

**Structure Decision**: Single-project Python CLI. The feature is implemented inside the existing `pocketcode` package with one new core persistence module and extensions to shared engine/CLI/Textual surfaces. Saved conversation state is treated as workspace runtime state under `.pocketcode/state/` rather than as a plugin resource or a large blob in `pocketcode.yml`.

## Complexity Tracking

> No Constitution violations — section not required.
