# Implementation Plan: Agents to Plugins — Core ReAct Agent Only

**Branch**: `004-agents-to-plugins` | **Date**: 2026-03-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/004-agents-to-plugins/spec.md`

## Summary

Remove all domain agents (`coder`, `architect`, `ask`) from the `core` plugin and replace them with a single purpose-built ReAct agent (`core::react`). Each domain agent is formally registered in its already-existing plugin (`coder`, `architect`, `asker`) with the full tool bindings it previously had in `core`. The `single_agent` flow and all its prompt files are deleted. `pocketcode.yml` and the `micromanager` manifest are updated to use new namespaced agent references. Handoff references across plugins use the fully-qualified `plugin::agent` form.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: pocketflow (custom Flow/Node framework), PyYAML, pytest
**Storage**: File-based — plugin directories with `plugin.yaml` manifests and `.py` agent modules
**Testing**: pytest — `tests/unit/` and `tests/integration/`
**Target Platform**: Linux (CLI application)
**Project Type**: CLI tool / plugin-driven agent framework
**Performance Goals**: `core::react` agent completes a tool call in < 5 s on a warm system (SC-005)
**Constraints**: Zero regressions in existing test suite (FR-009). No backward-compatible aliasing for removed agents.
**Scale/Scope**: 5 plugins (core, coder, architect, asker, micromanager); ~6 Python agent files; ~15 manifest entries.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Minimalist Orchestration — prefer native pocketflow Flow/Node | ✅ PASS | `react_agent.py` uses native `Flow` + `Node`; no custom workflow scaffolding added |
| II. User-Supplied Agent Plugins — plugins are self-contained with their own manifest | ✅ PASS | Each domain plugin gets its own complete agent entry in its own `plugin.yaml` |
| III. Shared Core Tools — system tools live in `pocketcode/tools/` | ✅ PASS | No tools are moved; domain plugins reference `core` tools by cross-plugin namespace |
| IV. Independent Testability — each User Story testable as standalone increment | ✅ PASS | Story 1 (core-only), Story 2 (single domain plugin), Story 3 (handoff) are each independently executable |

**Gate result**: PASS — proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/004-agents-to-plugins/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── plugin-agent-manifest.md   # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
pocketcode/plugins/
├── core/
│   ├── plugin.yaml                          # MODIFIED — remove coder/architect/ask; add react
│   ├── agents/
│   │   └── react_agent.py                   # NEW — purpose-built ReAct loop
│   ├── prompts/
│   │   ├── flows/
│   │   │   ├── orchestrator.md              # KEPT
│   │   │   └── single_agent.md              # DELETED (FR-013)
│   │   ├── nodes/
│   │   │   ├── orchestrator/orchestrate.md  # KEPT
│   │   │   └── single_agent/think.md        # DELETED (FR-013)
│   │   └── shared/                          # KEPT
│   └── tools/                               # UNCHANGED
│
.pocketcode/plugins/
├── coder/
│   ├── plugin.yaml                          # MODIFIED — rename agent coder→coder; add full tool list
│   └── agents/coder_agent.py                # KEPT (entry_fn: create_flow)
├── architect/
│   ├── plugin.yaml                          # MODIFIED — add glob_files, handoff targets
│   └── agents/architect_agent.py            # KEPT
├── asker/
│   ├── plugin.yaml                          # MODIFIED — fix plugin name (ask→asker); add full tool list
│   └── agents/asker_agent.py                # KEPT
└── micromanager/
    └── plugin.yaml                          # MODIFIED — update handoff_agents to namespaced form

pocketcode.yml                                # MODIFIED — default_agent: core::react; drop agent_runtime_workflow

tests/
├── integration/
│   └── test_pocketflow_plugin_discovery.py  # UPDATED — reflect new agent namespaces
└── unit/
    └── test_manifest_loader.py               # UPDATED if needed
```

**Structure Decision**: Single-project layout. The package-owned `core` plugin remains under `pocketcode/plugins/`, while non-core repo-shipped plugins live under `.pocketcode/plugins/`. The top-level config file is updated accordingly.

## Complexity Tracking

> No Constitution violations — section not required.
