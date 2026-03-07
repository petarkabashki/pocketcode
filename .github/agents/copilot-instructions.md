# PocketCoder Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-05

## Active Technologies
- Python 3.10+ + `pocketflow.py` (Core Orchestration), `PyYAML` (001-refactor-plugin-structure)
- PocketFlow Agents & Plugin Factory (002-pocketflow-agents)
- User-supplied agent folders (001-refactor-plugin-structure)
- Python 3.10+ + pocketflow, PyYAML, watchdog, textual, google-genai, openai, python-dotenv (003-unified-plugin-namespace)
- In-memory dicts (NamespaceRegistry snapshots); no persistent DB (003-unified-plugin-namespace)
- Python 3.12 + pocketflow (custom Flow/Node framework), PyYAML, pytest (004-agents-to-plugins)
- File-based — plugin directories with `plugin.yaml` manifests and `.py` agent modules (004-agents-to-plugins)
- Python ≥3.10 + `pocketflow` (Flow/Node), `pyyaml`, `textual`, `prompt_toolkit` (001-agent-default-profiles)
- Files — `.pocketcode/agent-profiles/*.yaml` (workspace-local, created on demand) (001-agent-default-profiles)
- Python 3.10+ (repo currently exercised on Python 3.12) + pocketflow, PyYAML, prompt_toolkit, textual, python-dotenv, pytest (005-cleanup-cli-consistency)
- File-based source tree and documentation artifacts; no new persistent storage (005-cleanup-cli-consistency)

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
├── plugins/         # Package-owned plugins (core lives here)
└── tools/           # Shared core tools
.pocketcode/
└── plugins/         # Workspace and repo-local plugins
```

## Commands

python3 -m pocketcode.main [args]
pytest tests/
ruff check .

## Code Style

Python 3.10+: Follow standard conventions, use `pocketflow` for complex agent logic.

## Recent Changes
- 005-cleanup-cli-consistency: Added Python 3.10+ (repo currently exercised on Python 3.12) + pocketflow, PyYAML, prompt_toolkit, textual, python-dotenv, pytest
- 001-agent-default-profiles: Added Python ≥3.10 + `pocketflow` (Flow/Node), `pyyaml`, `textual`, `prompt_toolkit`
- 004-agents-to-plugins: Added Python 3.12 + pocketflow (custom Flow/Node framework), PyYAML, pytest

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
