from __future__ import annotations

from pathlib import Path

from pocketcode.core.workspace_catalog import WorkspaceCatalog


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_workspace_namespace_registers_prompts_tools_and_programs(tmp_path):
    namespace_root = tmp_path / ".github"
    _write(
        namespace_root / "shared.prompt.md",
        """---
agent: github.reviewer
---
Shared rules
""",
    )
    _write(
        namespace_root / "echo.tool.py",
        """def echo_text(text):
    return {"text": text}
""",
    )
    _write(
        namespace_root / "reviewer.md",
        """---
description: Review the current resource_root.pocketcode.
tool_files:
  - echo.tool.py
prompt_files:
  - prompt:github.shared
---
Review carefully.

```vm
"ready" answer
```
""",
    )

    manager = WorkspaceCatalog(
        config={"runtime": {"workspace_paths": [str(namespace_root)]}},
        workspace_root=tmp_path,
    )
    manager.load()

    assert manager.prompts.resolve("github.shared") == "Shared rules"

    flow_def = manager.agents.resolve("github.reviewer")
    assert flow_def.description == "Review the current resource_root.pocketcode."
    assert flow_def.tools == ["github.echo_text"]
    assert "Review carefully." in flow_def.system_prompt
    assert "Shared rules" in flow_def.system_prompt
    assert flow_def.metadata["namespace"] == "github"
    assert Path(flow_def.metadata["namespace_root"]) == namespace_root.resolve()
    assert manager.tools.resolve("github.echo_text")(text="ok") == {"text": "ok"}


def test_workspace_namespace_ignores_legacy_asset_path_prefixes_in_names(tmp_path):
    namespace_root = tmp_path / ".github"
    _write(namespace_root / "sub.guide.prompt.md", "Prompt guide",)
    _write(
        namespace_root / "sub.checklist.md",
        """---
prompt_files:
  - prompt:github.sub.guide
---
Checklist agent.
""",
    )

    manager = WorkspaceCatalog(
        config={"runtime": {"workspace_paths": [str(namespace_root)]}},
        workspace_root=tmp_path,
    )
    manager.load()

    assert manager.prompts.resolve("github.sub.guide") == "Prompt guide"
    flow_def = manager.agents.resolve("github.sub.checklist")
    assert "Checklist agent." in flow_def.system_prompt
    assert "Prompt guide" in flow_def.system_prompt


def test_workspace_namespace_uses_adjacent_prompt_and_tool_files_by_default(tmp_path):
    namespace_root = tmp_path / ".github"
    _write(namespace_root / "review.prompt.md", "Adjacent prompt")
    _write(
        namespace_root / "review.tool.py",
        """def echo_text(text):
    return {"text": text}
""",
    )
    _write(
        namespace_root / "review.md",
        """---
description: Review with adjacent helpers.
---
Inline review prompt.

```vm
"done" answer
```
""",
    )

    manager = WorkspaceCatalog(
        config={"runtime": {"workspace_paths": [str(namespace_root)]}},
        workspace_root=tmp_path,
    )
    manager.load()

    flow_def = manager.agents.resolve("github.review")
    assert flow_def.tools == ["github.echo_text"]
    assert "Inline review prompt." in flow_def.system_prompt
    assert "Adjacent prompt" in flow_def.system_prompt
    assert manager.tools.resolve("github.echo_text")(text="ok") == {"text": "ok"}


def test_workspace_paths_can_mix_multiple_namespace_roots(tmp_path):
    namespace_root = tmp_path / ".github"
    nested_namespace = tmp_path / ".pocketcode" / "legacy"

    _write(namespace_root / "review.md", '---\n---\n```vm\n"ok" answer\n```\n')
    _write(nested_namespace / "planner.md", '---\n---\n```vm\n"legacy" answer\n```\n')

    manager = WorkspaceCatalog(
        config={"runtime": {"workspace_paths": [str(namespace_root), str(nested_namespace)]}},
        workspace_root=tmp_path,
    )
    manager.load()

    assert "github.review" in manager.flows
    assert "legacy.planner" in manager.flows


def test_resource_root_registers_hooks_from_grouped_collection(tmp_path):
    resource_root = tmp_path / ".pocketcode"
    _write(
        resource_root / "hook.memory" / "default.hook.md",
        """---
name: memory.default
description: Default memory hook.
---

```vm before_llm
"hook.before_llm" "memory" shared!
```
""",
    )

    manager = WorkspaceCatalog(config={}, workspace_root=tmp_path)
    manager.load()

    hook_def = manager.hooks.resolve("resource_root.pocketcode.memory.default")
    assert hook_def.name == "memory.default"
    assert hook_def.description == "Default memory hook."
    assert hook_def.phases == {"before_llm": '"hook.before_llm" "memory" shared!'}
