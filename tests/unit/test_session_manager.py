from pathlib import Path

from pocketcode.core.session_manager import SessionManager


class TestSessionManagerScaffold:
    def test_create_and_load_session_round_trip(self, tmp_path: Path):
        manager = SessionManager(tmp_path)

        record = manager.create_session(
            state={
                "active_agent": "core::agent",
                "debugger_breakpoints": ["until tool core.write_file"],
            }
        )
        loaded = manager.load_session(record.session_id)

        assert loaded.session_id == record.session_id
        assert loaded.active_agent == "core::agent"
        assert loaded.debugger_breakpoints == ["until tool core.write_file"]
        assert manager.storage_dir == tmp_path / ".pocketcode" / "state" / "sessions"

    def test_append_list_delete_and_clear_sessions(self, tmp_path: Path):
        manager = SessionManager(tmp_path)

        first = manager.create_session(title="First")
        second = manager.create_session(title="Second")
        manager.append_transcript_entry(first.session_id, role="user", content="hello")

        listed = manager.list_sessions()

        assert {item.session_id for item in listed} == {first.session_id, second.session_id}
        assert manager.load_session(first.session_id).transcript[0].content == "hello"

        assert manager.delete_session(second.session_id) is True
        assert manager.clear_sessions() == 1
        assert manager.list_sessions() == []


class TestSessionHistoryLifecycle:
    def test_update_session_persists_state_fields(self, tmp_path: Path):
        manager = SessionManager(tmp_path)
        record = manager.create_session(title="Working Session")

        updated = manager.update_session(
            record.session_id,
            active_agent="core::review",
            active_profile="review.safe",
            enabled_skills=["python-testing"],
        )

        assert updated.active_agent == "core::review"
        assert updated.active_profile == "review.safe"
        assert updated.enabled_skills == ["python-testing"]

    def test_list_sessions_returns_latest_first(self, tmp_path: Path):
        manager = SessionManager(tmp_path)
        first = manager.create_session(title="First")
        second = manager.create_session(title="Second")

        manager.append_transcript_entry(first.session_id, role="user", content="older")
        manager.append_transcript_entry(second.session_id, role="user", content="newer")

        listed = manager.list_sessions()

        assert listed[0].session_id == second.session_id
        assert listed[1].session_id == first.session_id

    def test_clear_sessions_respects_excluded_ids(self, tmp_path: Path):
        manager = SessionManager(tmp_path)
        active = manager.create_session(title="Active")
        stale = manager.create_session(title="Stale")

        removed = manager.clear_sessions(exclude_ids=[active.session_id])

        assert removed == 1
        assert manager.session_exists(active.session_id) is True
        assert manager.session_exists(stale.session_id) is False
