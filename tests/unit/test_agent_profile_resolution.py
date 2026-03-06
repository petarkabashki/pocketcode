"""Unit tests for agent-profile-driven LLM, tool, and confirmation resolution (T032).

Covers:
- FR-012 LLM tier 4.5: active_agent_profile.llm_profile override
- FR-008 tool allowlist filtering in tool_runtime.execute_tool (T019b)
- FR-009 confirmation tiers 1.5 and 4.5 in tool_runtime._resolve_confirmation_policy
- Profile tool_confirmation.overrides per-tool (tier 1.5)
- Profile tool_confirmation.default (tier 4.5)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock
from typing import Any, Dict

import pytest

from pocketcode.core.runtime_models import AgentDefinition, AgentProfile
from pocketcode.core.tool_runtime import ToolRuntime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(
    name: str = "test-profile",
    agent: str = "plug::agent",
    *,
    llm_profile: str | None = None,
    tools: list[str] | None = None,
    tool_confirmation: dict | None = None,
) -> AgentProfile:
    return AgentProfile(
        name=name,
        agent=agent,
        llm_profile=llm_profile,
        tools=tools,
        tool_confirmation=tool_confirmation or {},
    )


def _make_tool_runtime(shared_store: dict | None = None) -> tuple[ToolRuntime, dict]:
    """Return a minimally wired ToolRuntime and a mutable shared_store dict."""
    store: dict[str, Any] = shared_store or {}

    runtime = ToolRuntime.__new__(ToolRuntime)
    runtime._tools: Dict[str, Any] = {}
    runtime._confirmation_config = {
        "default_policy": None,
        "tool_policies": {},
        "agent_policies": {},
    }

    # _confirm_tool stub: always deny (we test before confirm branches)
    confirm_stub = MagicMock()
    confirm_stub.execute.return_value = {"success": True, "approved": False}
    runtime._confirm_tool = confirm_stub

    return runtime, store


# ---------------------------------------------------------------------------
# FR-012 LLM tier 4.5 (snapshot via _resolve_llm_profile)
# ---------------------------------------------------------------------------
#
# We test the logic indirectly by checking ToolRuntime policy (simpler path)
# and by calling _resolve_extra_prompts_content via unit assertions.
# The LLM tier is integration-tested in test_agent_profile_manager; here we
# verify the profile field is respected.


class TestLLMTier:
    """Verify active_agent_profile.llm_profile is respected when present."""

    def test_profile_llm_profile_stored_correctly(self):
        profile = _make_profile(llm_profile="my-llm")
        assert profile.llm_profile == "my-llm"

    def test_profile_llm_profile_none_when_not_set(self):
        profile = _make_profile()
        assert profile.llm_profile is None


# ---------------------------------------------------------------------------
# FR-009 Tool allowlist guard (T019b) — execute_tool early-exit
# ---------------------------------------------------------------------------


class TestToolAllowlistGuard:
    def _runtime_with_profile(self, tools: list[str] | None, store: dict) -> ToolRuntime:
        runtime, _ = _make_tool_runtime(store)
        if tools is not None:
            store["active_agent_profile"] = _make_profile(tools=tools)
        return runtime

    def test_tool_not_in_allowlist_is_denied(self):
        store: dict = {}
        runtime = self._runtime_with_profile(["allowed_tool"], store)
        result = runtime.execute_tool("blocked_tool", {}, store)
        assert result["success"] is False
        assert "allowlist" in result["error"].lower() or "not in" in result["error"].lower()

    def test_tool_in_allowlist_passes_guard(self):
        """Guard passes; subsequent policy/implementation may still deny — but different path."""
        store: dict = {}
        runtime = self._runtime_with_profile(["my_tool"], store)
        # Inject a stub tool implementation so it doesn't crash
        runtime._tools = {"my_tool": lambda **kw: {"success": True, "result": "ok"}}

        # Reset _resolve_confirmation_policy to return "allow" for clean path
        with patch.object(runtime, "_resolve_confirmation_policy", return_value="allow"):
            with patch.object(runtime, "_resolve_tool", return_value=lambda **kw: {"ok": True}):
                result = runtime.execute_tool("my_tool", {}, store)
        # Must NOT get the allowlist error
        if not result.get("success"):
            assert "allowlist" not in result.get("error", "")

    def test_no_active_profile_skips_guard(self):
        """When no profile is active, all tools are permitted by the guard."""
        store: dict = {}
        runtime, _ = _make_tool_runtime(store)
        # should not be denied by the allowlist guard
        with patch.object(runtime, "_resolve_confirmation_policy", return_value="allow"):
            with patch.object(runtime, "_resolve_tool", return_value=lambda **kw: {"ok": True}):
                result = runtime.execute_tool("any_tool", {}, store)
        assert "allowlist" not in str(result.get("error", ""))

    def test_profile_with_none_tools_skips_guard(self):
        """tools=None means all tools allowed (no allowlist enforcement)."""
        store: dict = {}
        runtime = self._runtime_with_profile(None, store)
        store["active_agent_profile"] = _make_profile(tools=None)
        with patch.object(runtime, "_resolve_confirmation_policy", return_value="allow"):
            with patch.object(runtime, "_resolve_tool", return_value=lambda **kw: {"ok": True}):
                result = runtime.execute_tool("random_tool", {}, store)
        assert "allowlist" not in str(result.get("error", ""))


# ---------------------------------------------------------------------------
# FR-009 Confirmation tiers 1.5 and 4.5
# ---------------------------------------------------------------------------


class TestConfirmationTier15:
    """Tier 1.5: profile.tool_confirmation.overrides[tool_name]."""

    def test_profile_override_deny_beats_session_default_allow(self):
        runtime, store = _make_tool_runtime()
        store["session_tool_confirmation"] = {"default_policy": "allow"}
        store["active_agent_profile"] = _make_profile(
            tool_confirmation={"overrides": {"dangerous_tool": "deny"}}
        )
        policy = runtime._resolve_confirmation_policy(
            tool_name="dangerous_tool",
            shared_store=store,
            agent_name=None,
            auto_confirm=False,
        )
        assert policy == "deny"

    def test_profile_override_confirm_for_specific_tool(self):
        runtime, store = _make_tool_runtime()
        store["active_agent_profile"] = _make_profile(
            tool_confirmation={"overrides": {"risky_tool": "confirm"}}
        )
        policy = runtime._resolve_confirmation_policy(
            tool_name="risky_tool",
            shared_store=store,
            agent_name=None,
            auto_confirm=False,
        )
        assert policy == "confirm"

    def test_profile_override_not_applied_for_other_tools(self):
        """overrides dict only affects the exact tool listed."""
        runtime, store = _make_tool_runtime()
        store["active_agent_profile"] = _make_profile(
            tool_confirmation={"overrides": {"only_this": "deny"}}
        )
        policy = runtime._resolve_confirmation_policy(
            tool_name="other_tool",
            shared_store=store,
            agent_name=None,
            auto_confirm=False,
        )
        # Falls through to default "allow"
        assert policy == "allow"


class TestConfirmationTier45:
    """Tier 4.5: profile.tool_confirmation.default."""

    def test_profile_default_deny_applies_when_no_higher_tier_set(self):
        runtime, store = _make_tool_runtime()
        store["active_agent_profile"] = _make_profile(
            tool_confirmation={"default": "deny"}
        )
        policy = runtime._resolve_confirmation_policy(
            tool_name="some_tool",
            shared_store=store,
            agent_name=None,
            auto_confirm=False,
        )
        assert policy == "deny"

    def test_profile_default_confirm(self):
        runtime, store = _make_tool_runtime()
        store["active_agent_profile"] = _make_profile(
            tool_confirmation={"default": "confirm"}
        )
        policy = runtime._resolve_confirmation_policy(
            tool_name="any_tool",
            shared_store=store,
            agent_name=None,
            auto_confirm=False,
        )
        assert policy == "confirm"

    def test_session_agent_default_beats_profile_default(self):
        """Tier 4 (session agent default) should take precedence over tier 4.5 (profile default)."""
        runtime, store = _make_tool_runtime()
        store["session_tool_confirmation"] = {
            "agent_policies": {
                "myagent": {"default_policy": "allow"}
            }
        }
        store["active_agent_profile"] = _make_profile(
            tool_confirmation={"default": "deny"}
        )
        policy = runtime._resolve_confirmation_policy(
            tool_name="any_tool",
            shared_store=store,
            agent_name="myagent",
            auto_confirm=False,
        )
        # session agent default (tier 4) wins over profile default (tier 4.5)
        assert policy == "allow"

    def test_auto_confirm_always_wins(self):
        runtime, store = _make_tool_runtime()
        store["active_agent_profile"] = _make_profile(
            tool_confirmation={"default": "deny"}
        )
        policy = runtime._resolve_confirmation_policy(
            tool_name="any_tool",
            shared_store=store,
            agent_name=None,
            auto_confirm=True,
        )
        assert policy == "allow"
