# PocketCoder Refactor Constitution

## Core Principles

### I. Minimalist Orchestration
Custom workflow logic must be minimized. Prefer native `pocketflow.py` Flow and Node patterns. Extensions are only permitted for mandatory protocol mapping.

### II. User-Supplied Agent Plugins
Plugins are treated as independent, user-supplied agents. Each plugin must be self-contained in its own folder with a `plugin.yaml` manifest.

### III. Shared Core Tools
System tools (git, filesystem, etc.) reside in `pocketcode/tools/` and provide a shared standard library for all agents.

### IV. Independent Testability
Each User Story must be testable as a standalone increment without requiring the full system implementation.

**Version**: 1.0.0 | **Ratified**: 2026-03-05
