Workspace layout:
- `.pocketcode/<namespace>.<flow>.md`: self-contained flow entry points.
- `.pocketcode/<module>.py`: PocketFlow flow factories referenced from Markdown.
- `.pocketcode/<namespace>.<prompt>.prompt.md`: namespace prompt files.
- `.pocketcode/<namespace>.<helper>.tool.py`: namespace-local tools.
- `.pocketcode/*.agent.yaml` / `.pocketcode/*.agent.md`: workspace agent profiles.
- `.pocketcode/*.prompt.md`: shared workspace prompts.
- `.pocketcode/*.tool.py`: shared workspace tools.
- `.pocketcode/skills/<skill_name>/SKILL.md`: workspace skills, with optional `tools/`, `scripts/`, `references/`, and `assets/`.

Flow Markdown schema:
```yaml
name: my_flow
description: Main flow.
module: my_flow.py
entry_fn: create_flow
llm_profile: gemini_default
tools:
  - my_tool
  - core.read_file
prompt_files:
  - system.prompt.md
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
name: my_namespace.my_flow
flow: my_namespace.my_flow
description: Optional profile description.
llm_profile: inherit-or-profile-name
tools:
  - core.read_file
extra_prompts:
  - prompt:resource_root.pocketcode.review
tool_confirmation:
  default: confirm
  overrides:
    core.execute_command: deny
```

Skill layout:
- Required: `.pocketcode/skills/<skill_name>/SKILL.md`.
- Optional: `.pocketcode/skills/<skill_name>/tools/`, `scripts/`, `references/`, `assets/`.
- Put operational instructions in `SKILL.md`; keep supporting material in the adjacent folders.

Portability rules:
- Do not rely on repository-only paths outside the active workspace.
- Prefer relative references inside the namespace or workspace you are editing.
- If a reusable implementation is unavailable in the current workspace, create the minimal local implementation needed.
- Keep documentation changes next to the feature when possible so the workspace remains self-describing.
