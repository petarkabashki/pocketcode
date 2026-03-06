from __future__ import annotations

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
