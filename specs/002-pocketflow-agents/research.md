# Research: PocketFlow Agents and Plugin Factory

**Feature**: [002-pocketflow-agents](../spec.md)
**Date**: 2026-03-05

## Research Task 1: Context Injection in PocketFlow
**Goal**: Find the cleanest way to inject `PluginContext` (tools, prompts) into the `shared` dictionary.

**Decision**: 
- We will provide a standard `PocketFlowAgent` wrapper in `pocketcode.core`.
- Before the flow starts (in `_run` or similar), the wrapper will populate a specific key in the `shared` store (e.g., `shared["_plugin"]`).
- Developers can use a `get_plugin_context(shared)` helper to access tools and prompts without having to know the exact key.

**Rationale**: This avoids modify the internal implementation of `pocketflow.py` (preserving its minimalist nature) while ensuring all nodes in the flow can access plugin resources via the shared dictionary they already receive.

---

## Research Task 2: Robust Plugin Loading with get_plugin()
**Goal**: Best practices for dynamic loading to avoid breaking the system on plugin errors.

**Decision**:
- `PluginManager` will use a try-except block when importing and calling the `get_plugin()` function.
- If the plugin's `__init__.py` doesn't exist or doesn't have `get_plugin()`, it falls back to the legacy `agent.yaml` loading.
- Errors during factory execution will be logged, and the plugin will be skipped, ensuring the rest of the application remains functional.

**Rationale**: This ensures backward compatibility while providing a resilient environment for user-supplied Python logic.

---

## Technical Patterns

### 1. The Plugin Class
```python
@dataclass
class Plugin:
    name: str
    tools: List[Callable] = field(default_factory=list)
    prompts: Dict[str, str] = field(default_factory=dict)
    agents: Dict[str, Flow] = field(default_factory=dict)
    # ... metadata
```

### 2. Context Access (in a Node)
```python
def exec(self, prep_res):
    shared = self.shared # Assuming Node has access or via param
    ctx = shared["_plugin"]
    # ctx.tools["my_tool"](...)
```

---

## Decision Log

| ID | Decision | Rationale | Alternatives |
|---|---|---|---|
| D1 | Use static Plugin class | Better type safety and discoverability | Raw dict / Dynamic attributes |
| D2 | Auto-injection into `shared` | Preserves PocketFlow simplicity | Decorators (too much magic) / Global state (dangerous) |
| D3 | Factory-first loading | Smooth transition to programmatic model | Parallel loading (too complex) |
