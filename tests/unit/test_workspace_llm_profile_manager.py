from __future__ import annotations

from pocketcode.core.workspace_llm_profile_manager import WorkspaceLlmProfileManager


class TestWorkspaceLlmProfileManager:
    def test_save_and_load_round_trip(self, tmp_path):
        manager = WorkspaceLlmProfileManager(tmp_path)

        manager.save(
            "fast-local",
            {
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "parameters": {"temperature": 0.1},
            },
        )
        manager.load()

        loaded = manager.get("fast-local")

        assert loaded is not None
        assert loaded["config"] == {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "parameters": {"temperature": 0.1},
        }
        assert loaded["source_path"].name == "fast-local.yaml"

    def test_clone_copies_config_to_new_workspace_file(self, tmp_path):
        manager = WorkspaceLlmProfileManager(tmp_path)
        manager.save(
            "fast-local",
            {
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "parameters": {"temperature": 0.1},
            },
        )
        manager.load()

        cloned = manager.clone(
            "fast-local",
            "fast-local-copy",
            {
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "parameters": {"temperature": 0.1},
            },
        )

        assert cloned["name"] == "fast-local-copy"
        assert cloned["config"]["model"] == "gemini-2.5-flash"
        assert cloned["source_path"].name == "fast-local-copy.yaml"
