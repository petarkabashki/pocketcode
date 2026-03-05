# Implementation Plan: Refactor Plugin Structure and Composition

**Branch**: `001-refactor-plugin-structure` | **Date**: 2026-03-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-refactor-plugin-structure/spec.md`

## Summary

This refactor transforms the application into a framework for user-supplied agent plugins. Each agent (e.g., architect, coder) is no longer hardcoded in `mode_flows/` but is a self-contained folder containing its persona and tools. Orchestration is strictly guided by the `pocketflow.py` implementation, using its native `Flow` and `Node` structures with minimal custom extensions.

## Technical Context

**Language/Version**: Python 3.10+  
**Primary Dependencies**: `pocketflow.py` (Core Orchestration), `PyYAML`  
**Storage**: User-supplied agent folders  
**Testing**: `pytest`
**Target Platform**: CLI / Terminal (Linux/macOS)
**Project Type**: CLI Framework / Multi-Agent Orchestrator  
**Performance Goals**: Plugin discovery and loading under 100ms.  
**Constraints**: No circular imports between `core` and `plugins`.  
**Scale/Scope**: Refactoring all 4 existing modes (architect, coder, Asker, Micromanager) into plugins.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Rule 1**: Maintain separation of concerns between `core` (orchestration) and `plugins` (capabilities).
- **Rule 2**: Each plugin must be independently deployable/loadable.
- **Rule 3**: Use `pocketflow` as the single source of truth for flow logic.

## Project Structure

### Documentation (this feature)

```text
specs/001-refactor-plugin-structure/
├── spec.md              # Re-clarified specification
├── plan.md              # This file
├── research.md          # All clarified unknowns (Phase 0)
├── data-model.md        # Agent Manifest and Tool Discovery (Phase 1)
├── quickstart.md        # How to create a self-contained agent (Phase 1)
└── contracts/           # Agent Manifest JSON Schema (Phase 1)
```

### Source Code (repository root)

```text
pocketcode/
├── core/                # Core orchestration (WorkflowRuntime, Engine)
├── tools/               # Shared Global Tools (Filesystem, Git, etc.)
├── plugins/             # Self-contained Plugins
│   ├── architect/
│   │   ├── agent.yaml
│   │   ├── prompts/
│   │   ├── tools/
│   │   └── workflows/
│   ├── coder/
│   └── ...
└── mode_flows/          # [DELETED/MIGRATED]
```

**Structure Decision**: Migration to a multi-plugin directory structure under `pocketcode/plugins/`, where each plugin encapsulates its own assets. Global tools remain in `pocketcode/tools/`. `mode_flows/` will be removed.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |
