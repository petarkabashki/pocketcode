# PocketCoder Documentation

PocketCoder is a highly configurable, agent-based AI assistant system.

## Topics

### Core Concepts
- [Architecture Overview](architecture.md) (Planned)
- [Prompt Engineering](prompts.md) (Planned)

### Plugins and Agents
- [Plugin Architecture](plugin_architecture.md)
- [PocketFlow Agents](pocketflow_agents.md)
- [Dynamic Tools](tools.md) (Planned)

## Quick Start
1. Configure your LLM provider in `pocketcode.yml`
2. Define a plugin with a factory function in `__init__.py`
3. Execute your agent with:
   `python -m pocketcode.main --agent <agent-name>`
