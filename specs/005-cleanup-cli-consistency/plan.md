# Implementation Plan: CLI Consistency Cleanup

**Branch**: `005-cleanup-cli-consistency` | **Date**: 2026-03-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/005-cleanup-cli-consistency/spec.md`

## Summary

Clean the CLI contract so universal help, suggestions, startup/status output, and command routing reflect one agent-centered public model. Remove workflow-era terminology and compatibility helpers, keep interface-only commands discoverable only within their interface, and back the resulting command/help contract with explicit tests.

## Technical Context

**Language/Version**: Python 3.10+ (repo currently exercised on Python 3.12)  
**Primary Dependencies**: pocketflow, PyYAML, prompt_toolkit, textual, python-dotenv, pytest  
**Storage**: File-based source tree and documentation artifacts; no new persistent storage  
**Testing**: pytest (`tests/unit/`, targeted CLI behavior tests, and any new Textual/help contract tests needed)  
**Target Platform**: Linux CLI environment with basic interactive CLI, one-shot CLI, and Textual UI  
**Project Type**: CLI tool / plugin-driven agent framework  
**Performance Goals**: No user-perceptible slowdown in command parsing, help display, or startup/status rendering; this feature is correctness-focused rather than throughput-focused  
**Constraints**: Remove deprecated routing/terminology helpers in the same feature; remove workflow from the supported public CLI model; keep interface-specific commands out of universal help/suggestion surfaces; preserve supported agent-centered behavior  
**Scale/Scope**: CLI layer across `pocketcode/main.py`, `pocketcode/cli/*.py`, related engine compatibility methods, and the corresponding docs/tests for command/help/discovery behavior

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Minimalist Orchestration | ✅ PASS | The feature removes obsolete CLI routing and terminology layers instead of adding new orchestration abstractions. |
| II. User-Supplied Agent Plugins | ✅ PASS | No plugin packaging or manifest contract is altered; the cleanup is limited to CLI presentation and routing. |
| III. Shared Core Tools | ✅ PASS | Tool ownership remains in existing locations; the feature only changes how commands/help surface those capabilities. |
| IV. Independent Testability | ✅ PASS | Story 1 (universal command/help contract), Story 2 (terminology cleanup), and Story 3 (internal compatibility removal) are each independently testable. |

**Gate result before Phase 0**: PASS — proceed to research.

**Gate result after Phase 1 design**: PASS — design preserves native structure, touches only CLI-facing surfaces, and remains independently testable.

## Project Structure

### Documentation (this feature)

```text
specs/005-cleanup-cli-consistency/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── cli-command-surface.md
└── tasks.md
```

### Source Code (repository root)

```text
pocketcode/
├── main.py                            # Startup output, basic CLI loop, one-shot command execution
├── cli/
│   ├── command_handler.py             # Universal command parsing, aliases, help text, suggestions
│   ├── completers.py                  # CLI completion helpers and any removable obsolete completions
│   ├── textual_app.py                 # Textual-only command handling and interface-specific discovery
│   ├── runtime_events.py              # Runtime event text, if terminology cleanup affects emitted labels
│   └── user_interaction.py            # Only if command/help wording changes require aligned interaction text
└── core/
    └── engine.py                      # Remaining compatibility helpers and status fields touched by CLI cleanup

docs/
├── modes_and_skills.md                # Interface and command documentation updates
├── pocketflow_agents.md               # Remove obsolete workflow wording if still user-facing
└── readme.md                          # Any top-level CLI/help wording updates if needed

tests/
└── unit/
    ├── test_command_handler.py        # Universal command/help/alias behavior
    └── test_cli_user_interaction.py   # Existing CLI interaction tests; extend only if needed
```

**Structure Decision**: Single-project Python CLI. The feature is implemented in-place within the existing `pocketcode` package and adjacent docs/tests. No new runtime subsystem is introduced; the change concentrates on command routing, help/discovery surfaces, terminology, and test coverage.

## Complexity Tracking

> No Constitution violations — section not required.
