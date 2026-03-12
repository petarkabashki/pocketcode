from __future__ import annotations

from pocketcode.core.markdown_profiles import SkillManager
from pocketcode.core.namespace_registry import NamespaceRegistry
class TestSkillManager:
    def test_loads_skill_markdown_and_tool_modules(self, tmp_path):
        skill_dir = tmp_path / ".pocketcode" / "skills" / "python-testing"
        (skill_dir / "tools").mkdir(parents=True, exist_ok=True)
        (skill_dir / "references").mkdir(parents=True, exist_ok=True)
        (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
        (skill_dir / "assets").mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: python-testing
description: Pytest workflow
tools:
  - core.read_file
extra_prompts:
  - references/style.md
---
Use pytest and target the smallest failing test first.
""",
            encoding="utf-8",
        )
        (skill_dir / "tools" / "pytest_tools.py").write_text(
            """
def run_pytest(shared_store=None):
    return {"success": True}
""",
            encoding="utf-8",
        )
        (skill_dir / "references" / "style.md").write_text("Style guide", encoding="utf-8")
        (skill_dir / "scripts" / "run_pytest.py").write_text("print('ok')", encoding="utf-8")
        (skill_dir / "assets" / "template.txt").write_text("asset", encoding="utf-8")

        manager = SkillManager(tmp_path)
        manager.load()

        skill = manager.get("python-testing")
        assert skill is not None
        assert skill.description == "Pytest workflow"
        assert skill.tool_refs == ["core.read_file"]
        assert skill.extra_prompts == ["references/style.md"]
        assert skill.inline_prompt == "Use pytest and target the smallest failing test first."
        assert sorted(skill.provided_tools.keys()) == ["skill.python_testing.run_pytest"]
        assert skill.references == ["references/style.md"]
        assert skill.scripts == ["scripts/run_pytest.py"]
        assert skill.assets == ["assets/template.txt"]

    def test_workspace_ignore_rules_filter_and_reinclude_skill_assets(self, tmp_path):
        skill_dir = tmp_path / ".pocketcode" / "skills" / "python-testing"
        (skill_dir / "tools").mkdir(parents=True, exist_ok=True)
        (skill_dir / "references").mkdir(parents=True, exist_ok=True)
        (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
        (skill_dir / "assets").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".pocketcode" / ".pocketcodeignore").write_text(
            "\n".join(
                [
                    "skills/python-testing/tools/*.py",
                    "!skills/python-testing/tools/keep.py",
                    "skills/python-testing/references/*.md",
                    "!skills/python-testing/references/keep.md",
                    "skills/hidden.disabled/",
                ]
            ),
            encoding="utf-8",
        )
        (skill_dir / "SKILL.md").write_text("---\nname: python-testing\n---\nUse it.\n", encoding="utf-8")
        (skill_dir / "tools" / "drop.py").write_text("def drop_tool():\n    return 'drop'\n", encoding="utf-8")
        (skill_dir / "tools" / "keep.py").write_text("def keep_tool():\n    return 'keep'\n", encoding="utf-8")
        (skill_dir / "references" / "drop.md").write_text("drop", encoding="utf-8")
        (skill_dir / "references" / "keep.md").write_text("keep", encoding="utf-8")
        hidden_dir = tmp_path / ".pocketcode" / "skills" / "hidden.disabled"
        hidden_dir.mkdir(parents=True, exist_ok=True)
        (hidden_dir / "SKILL.md").write_text("---\nname: hidden\n---\nHidden.\n", encoding="utf-8")

        manager = SkillManager(tmp_path)
        manager.load()

        skill = manager.get("python-testing")
        assert skill is not None
        assert sorted(skill.provided_tools.keys()) == ["skill.python_testing.keep_tool"]
        assert skill.references == ["references/keep.md"]
        assert manager.get("hidden") is None

    def test_skill_loader_normalizes_typed_refs(self, tmp_path):
        skill_dir = tmp_path / ".pocketcode" / "skills" / "python-testing"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: python-testing
tools:
  - tool:core.read_file
extra_prompts:
  - prompt:resource_root.pocketcode#review
---
Use it.
""",
            encoding="utf-8",
        )

        manager = SkillManager(tmp_path)
        manager.load()

        skill = manager.get("python-testing")
        assert skill is not None
        assert skill.tool_refs == ["core.read_file"]
        assert skill.extra_prompts == ["prompt:resource_root.pocketcode.review"]

    def test_skill_alias_folder_loads_skill(self, tmp_path):
        skill_dir = tmp_path / ".pocketcode" / "skill.python-testing"
        (skill_dir / "tools").mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: python-testing
---
Use it.
""",
            encoding="utf-8",
        )
        (skill_dir / "tools" / "pytest.tool.py").write_text(
            "def run_pytest():\n"
            "    return {'success': True}\n",
            encoding="utf-8",
        )

        manager = SkillManager(tmp_path)
        manager.load()

        skill = manager.get("python-testing")
        assert skill is not None
        assert sorted(skill.provided_tools.keys()) == ["skill.python_testing.run_pytest"]

    def test_invalid_typed_prompt_ref_skips_skill(self, tmp_path):
        skill_dir = tmp_path / ".pocketcode" / "skills" / "python-testing"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: python-testing
extra_prompts:
  - tool:core.read_file
---
Use it.
""",
            encoding="utf-8",
        )

        manager = SkillManager(tmp_path)
        manager.load()

        assert manager.get("python-testing") is None

    def test_skill_skips_when_tool_ref_is_missing_from_live_registry(self, tmp_path):
        skill_dir = tmp_path / ".pocketcode" / "skills" / "python-testing"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: python-testing
tools:
  - core.read_file
---
Use it.
""",
            encoding="utf-8",
        )

        manager = SkillManager(tmp_path, tool_registry=NamespaceRegistry())
        manager.load()

        assert manager.get("python-testing") is None

    def test_skill_skips_when_prompt_ref_is_missing_from_live_registry(self, tmp_path):
        skill_dir = tmp_path / ".pocketcode" / "skills" / "python-testing"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: python-testing
extra_prompts:
  - prompt:review
---
Use it.
""",
            encoding="utf-8",
        )

        manager = SkillManager(tmp_path, prompt_registry=NamespaceRegistry())
        manager.load()

        assert manager.get("python-testing") is None
