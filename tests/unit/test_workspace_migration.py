from __future__ import annotations

import json
from pathlib import Path

import yaml

from pocketcode.core.workspace_migration import ensure_workspace_migration, migrate_workspace, scan_workspace_migration


def test_migrate_workspace_rewrites_workspace_state(tmp_path: Path) -> None:
    workspace = tmp_path
    config_path = workspace / "pocketcode.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "llm": {"providers": {}, "profiles": {}},
                "runtime": {
                    "default_agent": "core::react",
                    "textual": {
                        "workspace_mode": "balanced",
                        "user_input_popups": True,
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    sessions_dir = workspace / ".pocketstate" / "sessions"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "one.json").write_text(
        json.dumps(
            {
                "session_id": "one",
                "workspace_root": str(workspace),
                "active_agent": "core::react",
                "session_profile_overrides": {"core::react": {"tools": ["core::read_file"]}},
            }
        ),
        encoding="utf-8",
    )
    resource_root = workspace / ".pocketcode"
    resource_root.mkdir()
    (resource_root / "review.agent.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "review",
                "flow": "core::react",
                "hooks": ["workspace.memory.default"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    skill_dir = resource_root / "skill.python-testing"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: python-testing\ntools:\n  - core::read_file\n---\nUse pytest.\n",
        encoding="utf-8",
    )
    (resource_root / "triage.md").write_text(
        "---\nname: triage\nprompts:\n  - prompts/review.md\n---\n```vm\n\"ok\" answer\n```\n",
        encoding="utf-8",
    )
    shim = resource_root / "coder.filesystem.tool.py"
    shim.write_text('"""Compatibility re-export for coder namespace filesystem tools."""\n', encoding="utf-8")

    report = migrate_workspace(workspace)

    assert report.changed is True
    migrated_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert migrated_config["runtime"]["default_agent"] == "core.react"
    assert migrated_config["runtime"]["textual"]["workspace_view"] == "balanced"
    assert migrated_config["runtime"]["textual"]["control_presentation"] == "modal"
    assert "workspace_mode" not in migrated_config["runtime"]["textual"]
    assert "user_input_popups" not in migrated_config["runtime"]["textual"]

    migrated_session = json.loads((sessions_dir / "one.json").read_text(encoding="utf-8"))
    assert migrated_session["active_agent"] == "core.react"
    assert "core.react" in migrated_session["session_profile_overrides"]
    migrated_agent = yaml.safe_load((resource_root / "agent.review" / "review.agent.yaml").read_text(encoding="utf-8"))
    assert migrated_agent["hooks"] == ["resource_root.pocketcode.memory.default"]
    migrated_flow = (resource_root / "triage.md").read_text(encoding="utf-8")
    assert "prompt_files:" in migrated_flow
    assert "\nprompts:\n" not in migrated_flow

    assert not (resource_root / "review.agent.yaml").exists()
    assert (resource_root / "agent.review" / "review.agent.yaml").exists()
    assert not skill_dir.exists()
    assert (resource_root / "skills" / "python-testing" / "SKILL.md").exists()
    assert not shim.exists()


def test_ensure_workspace_migration_requires_migration_when_auto_apply_is_disabled(tmp_path: Path) -> None:
    config_path = tmp_path / "pocketcode.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "llm": {"providers": {}, "profiles": {}},
                "runtime": {"textual": {"workspace_mode": "balanced"}},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    issues = scan_workspace_migration(tmp_path)
    assert issues

    try:
        ensure_workspace_migration(tmp_path, auto_apply=False)
    except Exception as exc:  # noqa: BLE001
        assert "Run `pocketcode --migrate-workspace`" in str(exc)
    else:
        raise AssertionError("Expected migration preflight to fail")
