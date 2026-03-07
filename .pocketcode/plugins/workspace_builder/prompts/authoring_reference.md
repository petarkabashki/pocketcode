Workspace layout:
- `.pocketcode/plugins/<plugin_name>/plugin.yaml`: plugin manifest.
- `.pocketcode/plugins/<plugin_name>/flows/*.py`: PocketFlow flow factories.
- `.pocketcode/plugins/<plugin_name>/agents/*.yaml`: composite agent profiles for plugin flows.
- `.pocketcode/plugins/<plugin_name>/prompts/**/*.md`: plugin prompt files.
- `.pocketcode/plugins/<plugin_name>/tools/*.py`: plugin-local tools.
- `.pocketcode/agents/*.yaml`: workspace agent profiles.
- `.pocketcode/prompts/**/*.md`: shared workspace prompts.
- `.pocketcode/tools/*.py`: shared workspace tools.
- `.pocketcode/skills/<skill_name>/SKILL.md`: workspace skills, with optional `tools/`, `scripts/`, `references/`, and `assets/`.

Plugin manifest schema:
```yaml
schema_version: 1
name: my_plugin
description: What the plugin does.

tools:
  my_tool: tools/my_tool.py:MyTool

flows:
  my_flow:
    module: flows/my_flow.py
    entry_fn: create_flow
    description: Main flow.
    llm_profile: gemini_default
    tools:
      - my_tool
      - core::read_file
    prompts:
      - prompts/system.md
```

Flow factory pattern:
```python
from __future__ import annotations

from typing import Any, Dict

from pocketflow import Flow, Node


class MyNode(Node):
    def prep(self, shared: Dict[str, Any]) -> str:
        return shared.get("initial_request", shared.get("task", ""))

    def exec(self, request: str) -> str:
        return request

    def post(self, shared: Dict[str, Any], prep_res: str, exec_res: str) -> str:
        if shared.get("_llm_router") is not None:
            return "llm_delegate"
        shared.setdefault("results", {})["my_flow"] = {
            "status": "pending_llm",
            "request": exec_res,
        }
        return "continue"


def create_flow() -> Flow:
    return Flow(start=MyNode())
```

Composite agent schema:
```yaml
name: my_plugin::my_flow
flow: my_plugin::my_flow
description: Optional profile description.
llm_profile: inherit-or-profile-name
tools:
  - core::read_file
extra_prompts:
  - prompts/review.md
tool_confirmation:
  default: confirm
  overrides:
    core::execute_command: deny
```

Skill layout:
- Required: `.pocketcode/skills/<skill_name>/SKILL.md`.
- Optional: `.pocketcode/skills/<skill_name>/tools/`, `scripts/`, `references/`, `assets/`.
- Put operational instructions in `SKILL.md`; keep supporting material in the adjacent folders.

Portability rules:
- Do not rely on repository-only paths outside the active workspace.
- Prefer relative references inside the plugin or workspace you are editing.
- If a reusable implementation is unavailable in the current workspace, create the minimal local implementation needed.
- Keep documentation changes next to the feature when possible so the workspace remains self-describing.
