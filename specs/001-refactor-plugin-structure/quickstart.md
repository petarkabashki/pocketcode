# Quickstart: Creating a Self-Contained Plugin

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Plugin Creation workflow

### 1. Structure

Create a folder under `.pocketcode/plugins/`:

```text
.pocketcode/plugins/my_plugin/
├── plugin.yaml
├── prompts/
│   └── main.md
├── tools/
│   └── my_tool.py
└── workflows/
    └── main.md
```

### 2. Manifest (`plugin.yaml`)

Define your plugin and its local assets:

```yaml
name: "my_plugin"
description: "A simple self-contained plugin"
version: "1.0.0"

tools:
  - id: "my_custom_tool"
    handler: "tools/my_tool.py:MyToolClass"

workflows:
  - id: "my_workflow"
    file: "workflows/main.md"
```

### 3. Workflow Definition (`workflows/main.md`)

Define your orchestration using standard markdown flow format (parsed into `pocketflow.Flow`):

```markdown
---
name: my_workflow
start: start
nodes:
  start:
    use: agent
    agent: my_agent
    prompt: prompts/main.md
  end:
    use: output
---
```

### 4. Local Tools (`tools/my_tool.py`)

Implement your tool using the `BaseTool` interface:

```python
from pocketcode.core.interfaces import BaseTool

class MyToolClass(BaseTool):
    @property
    def description(self) -> str:
        return "Does something custom"

    def execute(self, **kwargs) -> str:
        return "Success"
```
