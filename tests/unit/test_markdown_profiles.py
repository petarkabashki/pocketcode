from __future__ import annotations

from pocketcode.core.markdown_profiles import ModeManager, SkillManager


class TestModeManager:
    def test_loads_markdown_mode_frontmatter_and_body(self, tmp_path):
        modes_dir = tmp_path / ".pocketcode" / "modes"
        modes_dir.mkdir(parents=True, exist_ok=True)
        (modes_dir / "review.md").write_text(
            """---
name: review
description: Review mode
flow: core::react
llm_profile: smart
tools:
  - core.read_file
extra_prompts:
  - prompts/review.md
tool_confirmation:
  default: confirm
---
Review the code for regressions.
""",
            encoding="utf-8",
        )

        manager = ModeManager(tmp_path)
        manager.load()

        mode = manager.get("review")
        assert mode is not None
        assert mode.description == "Review mode"
        assert mode.flow == "core.react"
        assert mode.llm_profile == "smart"
        assert mode.tools == ["core.read_file"]
        assert mode.tools_specified is True
        assert mode.extra_prompts == ["prompts/review.md"]
        assert mode.tool_confirmation == {"default": "confirm", "overrides": {}}
        assert mode.inline_prompt == "Review the code for regressions."

    def test_workspace_ignore_rules_skip_disabled_or_ignored_modes(self, tmp_path):
        modes_dir = tmp_path / ".pocketcode" / "modes"
        modes_dir.mkdir(parents=True, exist_ok=True)
        (tmp_path / ".pocketcode" / ".pocketcodeignore").write_text("modes/skip.md\n", encoding="utf-8")
        (modes_dir / "skip.md").write_text("---\nname: skip\n---\nSkip me.\n", encoding="utf-8")
        (modes_dir / "hidden.disabled.md").write_text("---\nname: hidden\n---\nHide me.\n", encoding="utf-8")
        (modes_dir / "keep.md").write_text("---\nname: keep\n---\nKeep me.\n", encoding="utf-8")

        manager = ModeManager(tmp_path)
        manager.load()

        assert manager.get("skip") is None
        assert manager.get("hidden") is None
        assert manager.get("keep") is not None

        def test_mode_loader_normalizes_typed_refs(self, tmp_path):
                modes_dir = tmp_path / ".pocketcode" / "modes"
                modes_dir.mkdir(parents=True, exist_ok=True)
                (modes_dir / "review.md").write_text(
                        """---
name: review
flow: flow:core.react
tools:
    - tool:core.read_file
extra_prompts:
    - prompt:resource_root.pocketcode#review
---
Review it.
""",
                        encoding="utf-8",
                )

                manager = ModeManager(tmp_path)
                manager.load()

                mode = manager.get("review")
                assert mode is not None
                assert mode.flow == "core.react"
                assert mode.tools == ["core.read_file"]
                assert mode.extra_prompts == ["prompt:resource_root.pocketcode.review"]

        def test_invalid_typed_tool_ref_skips_mode(self, tmp_path):
                modes_dir = tmp_path / ".pocketcode" / "modes"
                modes_dir.mkdir(parents=True, exist_ok=True)
                (modes_dir / "bad.md").write_text(
                        """---
name: bad
flow: core::react
tools:
    - prompt:resource_root.pocketcode.review
---
Bad mode.
""",
                        encoding="utf-8",
                )

                manager = ModeManager(tmp_path)
                manager.load()

                assert manager.get("bad") is None


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
