# Research: Refactor Plugin Structure and Composition

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Unknowns & Clarifications

| Status | ID | Category | Topic | Finding/Decision |
| :--- | :--- | :--- | :--- | :--- |
| ✅ | 001 | Integration | Local Tool Loading | **Decision**: Use dynamic `importlib` for plugin tools; `core` handles fallback to global `pocketcode/tools/`. |
| ✅ | 002 | Patterns | Nested Flows | **Decision**: Use `pocketflow.Flow` for multi-agent loops; `WorkflowRuntime` handles recursion. |
| ✅ | 003 | Structure | Plugin Manifest | **Decision**: Standardize on `plugin.yaml` within each plugin folder. |
| ✅ | 004 | Dependencies | Global Tools | **Decision**: Global tools remain in `pocketcode/tools/` for now (Option B). |

## Findings

### Local Tool Discovery (Research Item 001)

- **Finding**: Plugins need a way to define their own Python tools.
- **Rationale**: Currently, `tool_runtime.py` likely expects a global registry.
- **Implementation**: `WorkflowRuntime` should search within the active plugin's `tools/` folder when resolving a `call_tool` request.

### Nested Flow Orchestration (Research Item 002)

- **Finding**: `pocketflow.py` supports nested flows by treating a `Flow` as a `Node`.
- **Rationale**: This matches the recursive nature of the system (e.g., orchestrator delegating to specialist).
- **Implementation**: The existing `WorkflowRuntime._run_flow_node` should be mapped cleanly to `pocketflow.Flow._run`.

### Plugin Manifest Standard (Research Item 003)

- **Finding**: Multiple asset types (prompts, tools, flows) require a central mapping.
- **Rationale**: `plugin.yaml` provides metadata and maps identifiers to local file paths.
- **Implementation**: Standardize the structure of `plugin.yaml` to include `name`, `capabilities`, `tools`, and `workflows`.

## Best Practices

- **Separation of Concerns**: Plugins specify **"What"** (prompts, workflows), Core specifies **"How"** (orchestration, LLM routing).
- **Loose Coupling**: Plugins should only interact with each other via `handoff` or nesting, never direct imports.
