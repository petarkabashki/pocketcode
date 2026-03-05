# Implementation Plan: Unified Plugin Namespace Architecture

**Branch**: `003-unified-plugin-namespace` | **Date**: 2026-03-05 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/003-unified-plugin-namespace/spec.md`

## Summary

Consolidate PocketCoder's resource model into a single plugin-scoped namespace where every tool, agent, and prompt is addressed as `plugin_name.resource_name`. Declarative workflows are eliminated — all execution graphs are expressed as PocketFlow `Flow` objects declared via `module:` + `entry_fn:` factory references in a unified `plugin.yaml` (schema_version: 1) manifest. The `PluginManager` evolves into a `NamespaceRegistry` with atomic snapshot-swap hot-reload and Python `logging`-based WARNING/ERROR observability. Core tool implementations are physically relocated into the core plugin's `tools/` directory.

---

## Technical Context

**Language/Version**: Python 3.10+  
**Primary Dependencies**: pocketflow, PyYAML, watchdog, textual, google-genai, openai, python-dotenv  
**Storage**: In-memory dicts (NamespaceRegistry snapshots); no persistent DB  
**Testing**: pytest — existing `tests/integration/` suite passes unmodified; new unit tests in `tests/unit/`  
**Target Platform**: Linux/macOS developer workstation  
**Project Type**: CLI framework / plugin runtime  
**Performance Goals**: Hot-reload registry rebuild ≤ 5 s; qualified name lookup O(1)  
**Constraints**: No process restart for hot-reload; in-flight sessions must not be interrupted; zero silent name-collision overwrites  
**Scale/Scope**: ≥ 4 simultaneously active plugins; ~15 core tools; ~5 built-in agents

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Minimalist Orchestration** — prefer native PocketFlow Flow/Node | ✅ PASS | All agents use PocketFlow `Flow` + `Node` via `module:` + `entry_fn:` factory. No custom workflow DSL added. |
| **II. User-Supplied Agent Plugins — `agent.yaml` per plugin** | ⚠️ JUSTIFIED VIOLATION | Spec explicitly replaces `agent.yaml` with unified `plugin.yaml` (schema_version: 1). Legacy `agent.yaml` files are supported with a migration WARNING for one release cycle. Violation is justified: a single manifest format is the core deliverable. |
| **III. Shared Core Tools in `pocketcode/tools/`** | ⚠️ JUSTIFIED VIOLATION | Spec requires tool implementations to be physically in `pocketcode/plugins/core/tools/`. The shared library in `pocketcode/tools/` is retained as an import-only library; all registrations originate from the core plugin manifest. Violation is justified: it is P1 and the structural foundation of the namespace model. |
| **IV. Independent Testability** | ✅ PASS | Each user story has a defined independent test path in the spec. |

**Gate result: PROCEED** — both violations are load-bearing to the feature goal and explicitly designed in the spec.

---

## Project Structure

### Documentation (this feature)

```text
specs/003-unified-plugin-namespace/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/
│   ├── manifest-v1.md   ← plugin.yaml schema contract
│   └── registry-api.md  ← NamespaceRegistry Python interface contract
└── tasks.md             ← Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
pocketcode/
├── core/
│   ├── namespace_registry.py     # NEW — NamespaceRegistry with snapshot-swap hot-reload
│   ├── plugin_manager.py         # MODIFIED — delegates storage to NamespaceRegistry
│   ├── manifest_loader.py        # NEW — schema_version-aware YAML parser + migration shim
│   ├── runtime_models.py         # MODIFIED — AgentDefinition adds module/entry_fn fields
│   ├── watcher.py                # MODIFIED — triggers snapshot-swap on file change
│   └── workflow_runtime.py       # MODIFIED — remove workflow-specific paths; all agents via Flow
│
└── plugins/
    └── core/
        ├── plugin.yaml           # MODIFIED — adds schema_version: 1; tools → local refs
        └── tools/                # NEW — physical home for core tool implementations
            ├── filesystem.py     # MOVED/WRAPPED from pocketcode/tools/filesystem.py
            ├── git.py
            ├── search.py
            ├── system.py
            └── user_input.py

pocketcode/tools/                 # RETAINED — shared import library (not a registration source)

tests/
├── integration/                  # EXISTING — must pass unmodified (SC-001)
└── unit/
    ├── test_namespace_registry.py   # NEW
    ├── test_manifest_loader.py      # NEW
    └── test_plugin_manager.py       # NEW (extended)
```

**Structure Decision**: Single project layout within `pocketcode/`. The primary new file is `namespace_registry.py`; `manifest_loader.py` is extracted from `plugin_manager.py` for testability.

---

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| Constitution II — `plugin.yaml` replaces `agent.yaml` | Single manifest format is the core deliverable; inconsistency between formats is the root problem | Keeping both formats perpetuates the inconsistency and blocks namespacing |
| Constitution III — core tool files move into core plugin | User Story 1 (P1) requires implementations to be physically in the plugin directory; namespace references need a canonical home | Retaining `pocketcode/tools/` as canonical source makes the core plugin not self-contained, violating SC-006 |
