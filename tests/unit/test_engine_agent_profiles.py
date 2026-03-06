from __future__ import annotations

from pathlib import Path

from pocketcode.core.engine import PocketCodeEngine
from pocketcode.core.runtime_models import AgentProfile


class _ProfileManagerStub:
    def __init__(self, profiles: dict[str, AgentProfile]):
        self._profiles = profiles

    def get(self, name: str):
        return self._profiles.get(name)

    def list(self):
        return sorted(self._profiles.values(), key=lambda p: p.name)

    def clone(self, src_name: str, new_name: str):
        profile = self._profiles[src_name]
        cloned = AgentProfile(
            name=new_name,
            agent=profile.agent,
            description=profile.description,
            llm_profile=profile.llm_profile,
            extra_prompts=list(profile.extra_prompts),
            tools=list(profile.tools) if profile.tools is not None else None,
            tool_confirmation=dict(profile.tool_confirmation),
            source="workspace",
        )
        self._profiles[new_name] = cloned
        return cloned


class _EditableProfileManagerStub(_ProfileManagerStub):
    def __init__(self, profiles: dict[str, AgentProfile]):
        super().__init__(profiles)
        self.saved_profile: AgentProfile | None = None
        self.reload_count = 0

    def save(self, profile: AgentProfile):
        self.saved_profile = profile
        self._profiles[profile.name] = profile

    def reload(self, agent_definitions: dict):
        self.reload_count += 1


class _PluginsWithToolResolution:
    def __init__(self):
        self.agents = {"coder::coder": object()}
        self.resolve_call_count = 0

    def resolve_tools_for_agent(self, agent_name: str):
        self.resolve_call_count += 1
        return ["tool.b", "tool.a"]


class TestEngineAgentProfiles:
    def test_set_active_agent_profile_switches_current_agent(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        profile = AgentProfile(name="coder.safe", agent="coder::coder", source="workspace")
        engine._agent_profile_manager = _ProfileManagerStub({"coder.safe": profile})
        engine._plugins = type("Plugins", (), {"agents": {"coder::coder": object()}})()
        engine.current_agent = None
        engine.active_agent_profile = None

        engine.set_active_agent_profile("coder.safe")

        assert engine.current_agent == "coder::coder"
        assert engine.active_agent_profile is profile

    def test_set_active_agent_profile_rejects_unknown_target_agent(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        profile = AgentProfile(name="ghost.safe", agent="ghost::ghost", source="workspace")
        engine._agent_profile_manager = _ProfileManagerStub({"ghost.safe": profile})
        engine._plugins = type("Plugins", (), {"agents": {}})()
        engine.current_agent = None
        engine.active_agent_profile = None

        try:
            engine.set_active_agent_profile("ghost.safe")
        except ValueError as exc:
            assert "unknown agent" in str(exc).lower()
        else:
            raise AssertionError("Expected ValueError for profile targeting an unknown agent")

    def test_list_agent_profiles_can_filter_by_agent(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._agent_profile_manager = _ProfileManagerStub(
            {
                "coder.safe": AgentProfile(name="coder.safe", agent="coder::coder"),
                "asker.fast": AgentProfile(name="asker.fast", agent="asker::asker"),
            }
        )

        assert engine.list_agent_profiles("coder::coder") == ["coder.safe"]
        assert engine.list_agent_profiles() == ["asker.fast", "coder.safe"]

    def test_update_agent_profile_persists_workspace_profile(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        profile = AgentProfile(
            name="coder.safe",
            agent="coder::coder",
            llm_profile=None,
            extra_prompts=["prompts/base.md"],
            tools=["filesystem::read_file"],
            tool_confirmation={"overrides": {"filesystem::delete_file": "deny"}},
            source="workspace",
            source_path=Path("/tmp/coder.safe.yaml"),
        )
        manager = _EditableProfileManagerStub({"coder.safe": profile})
        engine._agent_profile_manager = manager
        engine._plugins = type("Plugins", (), {"agents": {"coder::coder": object()}})()
        engine._llm_router = type(
            "Router",
            (),
            {"resolve_profile_config": staticmethod(lambda name: {"profile_name": name})},
        )()
        engine.active_agent_profile = profile
        engine._normalize_confirmation_policy = PocketCodeEngine._normalize_confirmation_policy.__get__(
            engine,
            PocketCodeEngine,
        )

        updated = engine.update_agent_profile(
            "coder.safe",
            llm_profile="gemini_fast",
            tools=["filesystem::read_file", "search::web_search"],
            extra_prompts=["prompts/base.md", "prompts/review.md"],
            tool_confirmation_default="confirm",
        )

        assert manager.saved_profile is not None
        assert manager.saved_profile.llm_profile == "gemini_fast"
        assert manager.saved_profile.tools == ["filesystem::read_file", "search::web_search"]
        assert manager.saved_profile.extra_prompts == ["prompts/base.md", "prompts/review.md"]
        assert manager.saved_profile.tool_confirmation == {
            "default": "confirm",
            "overrides": {"filesystem::delete_file": "deny"},
        }
        assert manager.reload_count == 1
        assert updated is manager.saved_profile
        assert engine.active_agent_profile is manager.saved_profile

    def test_list_tools_for_agent_caches_unfiltered_results(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._plugins = _PluginsWithToolResolution()
        engine.active_agent_profile = None
        engine._agent_tools_cache = {}

        first = engine.list_tools_for_agent("coder::coder")
        second = engine.list_tools_for_agent("coder::coder")

        assert first == ["tool.a", "tool.b"]
        assert second == ["tool.a", "tool.b"]
        assert engine._plugins.resolve_call_count == 1
