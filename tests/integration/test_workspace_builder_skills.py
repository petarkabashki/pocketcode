from pathlib import Path

from pocketcode.core.markdown_profiles import SkillManager


def test_workspace_builder_skill_pack_is_discoverable():
    workspace_root = Path(__file__).parent.parent.parent.resolve()

    manager = SkillManager(workspace_root)
    manager.load()

    expected = {
        "pocketcode-workspace-builder",
        "pocketcode-graph-authoring",
        "pocketcode-plugin-authoring",
        "pocketcode-profiles-prompts",
        "pocketcode-tools-runtime",
        "pocketcode-workspace-assets",
    }

    loaded = {skill.name for skill in manager.list()}
    assert expected.issubset(loaded)

    umbrella = manager.get("pocketcode-workspace-builder")
    assert umbrella is not None
    assert "references/source-map.md" in umbrella.references
