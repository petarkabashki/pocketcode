# Implementation Plan: PocketFlow Agents and Plugin Factory

**Branch**: `002-pocketflow-agents` | **Date**: 2026-03-05 | **Spec**: [specs/002-pocketflow-agents/spec.md](specs/002-pocketflow-agents/spec.md)
**Input**: Feature specification from `/specs/002-pocketflow-agents/spec.md`

## Summary
The goal is to transition agent definitions from static YAML/Markdown files to programmatic Python-based `pocketflow.Flow` objects. This will be achieved by introducing a `Plugin` class and updating the `PluginManager` to discover and invoke a `get_plugin()` factory function within each plugin's module.

## Technical Context

**Language/Version**: Python 3.10+  
**Primary Dependencies**: `pocketflow.py` (internal), `pyyaml`, `logging`  
**Storage**: N/A (Dynamic loading into memory)  
**Testing**: `pytest`  
**Target Platform**: Linux/macOS/Windows (CLI)
**Project Type**: CLI / Agentic Framework  
**Performance Goals**: Plugin loading < 500ms for 20 plugins.  
**Constraints**: Must support both sync (`Flow`) and async (`AsyncFlow`) agents.  
**Scale/Scope**: Replace legacy `agent.yaml` logic for all internal and external plugins.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check |
| :--- | :--- |
| **I. Minimalist Orchestration** | **PASS**: Using `pocketflow` native patterns directly. |
| **II. User-Supplied Agent Plugins** | **PASS**: Factory function keeps plugins self-contained and programmatic. |
| **III. Shared Core Tools** | **PASS**: Core tools remain in `pocketcode/tools/` and accessible via context. |
| **IV. Independent Testability** | **PASS**: Each story is testable as a standalone increment. |

## Project Structure

### Documentation (this feature)

```text
specs/002-pocketflow-agents/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
pocketcode/
├── core/
│   ├── interfaces.py    # Add Plugin and PluginContext classes
│   ├── plugin_manager.py# Update to support get_plugin() factory
│   └── agent_runtime.py # Add support for pocketflow.Flow execution
└── plugins/
    └── template/        # Example of new factory-based plugin
```

**Structure Decision**: Standard single-project structure extending the existing `pocketcode/core` modules and providing examples in `pocketcode/plugins/`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | | |
