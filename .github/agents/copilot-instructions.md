# PocketCoder Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-05

## Active Technologies
- Python 3.10+ + `pocketflow.py` (Core Orchestration), `PyYAML` (001-refactor-plugin-structure)
- PocketFlow Agents & Plugin Factory (002-pocketflow-agents)
- User-supplied agent folders (001-refactor-plugin-structure)
- Python 3.10+ + pocketflow, PyYAML, watchdog, textual, google-genai, openai, python-dotenv (003-unified-plugin-namespace)
- In-memory dicts (NamespaceRegistry snapshots); no persistent DB (003-unified-plugin-namespace)

## Core Patterns

### Plugin Factory (002-pocketflow-agents)
Plugins should implement a `get_plugin(config: Dict[str, Any]) -> Plugin` factory function in their `__init__.py`. 
The `Plugin` container holds tools, prompts, and `pocketflow.Flow` agents.

### PocketFlow Context
All `pocketflow.Flow` nodes receive a `PluginContext` in `shared['_plugin']`. 
Use `ctx = get_plugin_context(shared)` to access local prompts and tools:
```python
def my_node(shared):
    ctx = get_plugin_context(shared)
    prompt = ctx.get_prompt("system")
    # ... logic ...
```

## Project Structure

```text
pocketcode/
├── core/            # Framework engine and interfaces
├── cli/             # Textual-based CLI and command handlers
├── plugins/         # Built-in and user plugins (factory-based)
└── tools/           # Shared core tools
```

## Commands

python3 -m pocketcode.main [args]
pytest tests/
ruff check .

## Code Style

Python 3.10+: Follow standard conventions, use `pocketflow` for complex agent logic.

## Recent Changes
- 003-unified-plugin-namespace: Added Python 3.10+ + pocketflow, PyYAML, watchdog, textual, google-genai, openai, python-dotenv
- 002-pocketflow-agents: Introduced programmatic PocketFlow agents and `get_plugin` factory registration.
- 001-refactor-plugin-structure: Added Python 3.10+ + `pocketflow.py` (Core Orchestration), `PyYAML`

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
