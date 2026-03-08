"""Unit tests for AgentProfileManager (T031).

Covers:
- Synthesised default profile generation from agent definitions
- Explicit plugin-declared default_agent_profile merging
- Workspace YAML file loading with correct precedence
- Collision handling (plugin > workspace > synthesised)
- Malformed YAML graceful handling
- get() / list() / clone() / save()
- reload() clears and re-populates the registry
"""

from __future__ import annotations

import yaml

from pocketcode.core.agent_profile_manager import AgentProfileManager
from pocketcode.core.runtime_models import AgentDefinition, AgentProfile


def _make_agent_def(
    plugin_name: str,
    agent_name: str,
    *,
    llm_profile: str | None = None,
    default_agent_profile: AgentProfile | None = None,
) -> tuple[str, AgentDefinition]:
    """Return (qualified_name, AgentDefinition) for test fixtures."""
    qname = f"{plugin_name}::{agent_name}"
    defn = AgentDefinition(
        name=agent_name,
        llm_profile=llm_profile,
        default_agent_profile=default_agent_profile,
    )
    return qname, defn


# ---------------------------------------------------------------------------
# TestSynthesisedDefaults
# ---------------------------------------------------------------------------


class TestSynthesisedDefaults:
    def test_synthesised_profile_created_per_agent(self, tmp_path):
        qname, defn = _make_agent_def("myplugin", "myagent")
        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        profile = apm.get(qname)
        assert profile is not None
        assert profile.name == qname
        assert profile.agent == qname
        assert profile.source == "synthesised"

    def test_synthesised_profile_inherits_no_llm(self, tmp_path):
        qname, defn = _make_agent_def("p", "a")
        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})
        assert apm.get(qname).llm_profile is None

    def test_synthesised_profile_has_empty_tools(self, tmp_path):
        qname, defn = _make_agent_def("p", "a")
        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})
        profile = apm.get(qname)
        assert profile.tools is None
        assert profile.extra_prompts == []

    def test_multiple_agents_each_get_own_default(self, tmp_path):
        defs = {}
        for agent in ("alpha", "beta", "gamma"):
            qname, defn = _make_agent_def("plug", agent)
            defs[qname] = defn
        apm = AgentProfileManager(tmp_path)
        apm.load(defs)
        profiles = apm.list()
        assert len(profiles) == 3


# ---------------------------------------------------------------------------
# TestPluginDeclaredProfile
# ---------------------------------------------------------------------------


class TestPluginDeclaredProfile:
    def test_plugin_declared_profile_wins_over_synthesised(self, tmp_path):
        qname, defn = _make_agent_def("p", "a")
        declared = AgentProfile(
            name="p::a:custom",
            flow=qname,
            llm_profile="gpt-4",
            source="plugin",
        )
        defn.default_agent_profile = declared

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        # Plugin-declared name must exist with the right LLM
        plug = apm.get("p::a:custom")
        assert plug is not None
        assert plug.llm_profile == "gpt-4"
        assert plug.source == "plugin"
        # No separate synthesised entry — plugin declared its own explicit profile.
        assert apm.get(qname) is None

    def test_plugin_name_fallback_to_qualified(self, tmp_path):
        qname, defn = _make_agent_def("myplugin", "myagent")
        # Simulate plugin YAML where name field is absent (plugin_manager sets name=qname)
        declared = AgentProfile(name=qname, flow=qname, source="plugin")
        defn.default_agent_profile = declared

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        profile = apm.get(qname)
        assert profile.source == "plugin"

    def test_plugin_local_agent_yaml_loads_and_inherits_flow_defaults(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent", llm_profile="gemini_fast")
        defn.tools = ["tool.read", "tool.write"]
        plugin_root = tmp_path / "plugins" / "plug"
        agents_dir = plugin_root / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "agent.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "plug::agent",
                    "flow": qname,
                    "description": "Plugin-local composite agent.",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        defn.metadata = {"plugin_root": str(plugin_root)}

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        profile = apm.get("plug::agent")
        assert profile is not None
        assert profile.source == "plugin"
        assert profile.flow == qname.replace("::", ".")
        assert profile.llm_profile == "gemini_fast"
        assert profile.tools == ["tool.read", "tool.write"]

    def test_plugin_local_agent_yaml_normalizes_legacy_flow_reference(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        plugin_root = tmp_path / "plugins" / "plug"
        agents_dir = plugin_root / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "agent.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "plug::agent",
                    "flow": qname,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        defn.metadata = {"plugin_root": str(plugin_root)}

        apm = AgentProfileManager(tmp_path)
        apm.load({qname.replace("::", "."): defn})

        profile = apm.get("plug::agent")
        assert profile is not None
        assert profile.flow == "plug.agent"

    def test_plugin_agent_yaml_respects_plugin_ignore_rules(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        plugin_root = tmp_path / "plugins" / "plug"
        agents_dir = plugin_root / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (tmp_path / ".pocketcodeignore").write_text("plug/agents/*.yaml\n!plug/agents/keep.yaml\n", encoding="utf-8")
        (agents_dir / "drop.yaml").write_text(
            yaml.safe_dump({"name": "drop", "flow": qname}, sort_keys=False),
            encoding="utf-8",
        )
        (agents_dir / "keep.yaml").write_text(
            yaml.safe_dump({"name": "keep", "flow": qname}, sort_keys=False),
            encoding="utf-8",
        )
        defn.metadata = {"plugin_root": str(plugin_root)}

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        assert apm.get("drop") is None
        assert apm.get("keep") is not None


# ---------------------------------------------------------------------------
# TestWorkspaceYamlLoading
# ---------------------------------------------------------------------------


class TestWorkspaceYamlLoading:
    def _write_ws_profile(self, profiles_dir, filename, data: dict):
        profiles_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = profiles_dir / filename
        yaml_path.write_text(yaml.dump(data))
        return yaml_path

    def test_workspace_yaml_loaded(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        ws_profiles = tmp_path / ".pocketcode" / "agent-profiles"
        self._write_ws_profile(
            ws_profiles,
            "custom.yaml",
            {"name": "custom", "flow": qname},
        )
        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        assert apm.get("custom") is not None

    def test_workspace_profile_source_is_workspace(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        ws_profiles = tmp_path / ".pocketcode" / "agent-profiles"
        self._write_ws_profile(ws_profiles, "ws.yaml", {"name": "ws", "flow": qname})
        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        assert apm.get("ws").source == "workspace"

    def test_workspace_ignore_rules_skip_disabled_and_ignored_agent_files(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        (tmp_path / ".pocketcode").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".pocketcode" / ".pocketcodeignore").write_text(
            "\n".join(
                [
                    "agents/*.yaml",
                    "!agents/keep.yaml",
                ]
            ),
            encoding="utf-8",
        )
        ws_profiles = tmp_path / ".pocketcode" / "agents"
        self._write_ws_profile(ws_profiles, "drop.yaml", {"name": "drop", "flow": qname})
        self._write_ws_profile(ws_profiles, "keep.yaml", {"name": "keep", "flow": qname})
        self._write_ws_profile(ws_profiles, "hidden.disabled.yaml", {"name": "hidden", "flow": qname})

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        assert apm.get("drop") is None
        assert apm.get("keep") is not None
        assert apm.get("hidden") is None

    def test_workspace_beats_synthesised_same_name(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        ws_profiles = tmp_path / ".pocketcode" / "agent-profiles"
        # workspace file claims the same name as the synthesised profile
        self._write_ws_profile(ws_profiles, "collision.yaml", {"name": qname, "flow": qname, "llm_profile": "ws-llm"})
        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        profile = apm.get(qname)
        assert profile.source == "workspace"
        assert profile.llm_profile == "ws-llm"

    def test_plugin_beats_workspace_same_name(self, tmp_path, caplog):
        qname, defn = _make_agent_def("plug", "agent")
        declared = AgentProfile(name="shared", flow=qname, llm_profile="plugin-llm", source="plugin")
        defn.default_agent_profile = declared

        ws_profiles = tmp_path / ".pocketcode" / "agent-profiles"
        self._write_ws_profile(ws_profiles, "ws.yaml", {"name": "shared", "flow": qname, "llm_profile": "ws-llm"})

        apm = AgentProfileManager(tmp_path)
        with caplog.at_level("WARNING"):
            apm.load({qname: defn})

        profile = apm.get("shared")
        assert profile.source == "plugin"
        assert profile.llm_profile == "plugin-llm"


# ---------------------------------------------------------------------------
# TestMalformedYaml
# ---------------------------------------------------------------------------


class TestMalformedYaml:
    def test_malformed_yaml_skipped_with_warning(self, tmp_path, caplog):
        ws_profiles = tmp_path / ".pocketcode" / "agent-profiles"
        ws_profiles.mkdir(parents=True, exist_ok=True)
        bad = ws_profiles / "bad.yaml"
        bad.write_text("key: [unclosed")

        qname, defn = _make_agent_def("p", "a")
        apm = AgentProfileManager(tmp_path)
        with caplog.at_level("WARNING"):
            apm.load({qname: defn})

        assert any("bad.yaml" in r.message or "bad" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# TestGetAndList
# ---------------------------------------------------------------------------


class TestGetAndList:
    def test_get_missing_returns_none(self, tmp_path):
        apm = AgentProfileManager(tmp_path)
        apm.load({})
        assert apm.get("does-not-exist") is None

    def test_list_returns_sorted(self, tmp_path):
        defs = {}
        for name in ("z", "a", "m"):
            qname, defn = _make_agent_def("p", name)
            defs[qname] = defn
        apm = AgentProfileManager(tmp_path)
        apm.load(defs)
        names = [p.name for p in apm.list()]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# TestClone
# ---------------------------------------------------------------------------


class TestClone:
    def test_clone_creates_new_profile(self, tmp_path):
        qname, defn = _make_agent_def("p", "a")
        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})
        apm.clone(qname, "cloned")
        assert apm.get("cloned") is not None

    def test_clone_writes_yaml_file(self, tmp_path):
        qname, defn = _make_agent_def("p", "a")
        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})
        apm.clone(qname, "cloned")
        yaml_file = tmp_path / ".pocketcode" / "agents" / "cloned.yaml"
        assert yaml_file.exists()

    def test_clone_missing_source_raises(self, tmp_path):
        apm = AgentProfileManager(tmp_path)
        apm.load({})
        import pytest
        with pytest.raises(ValueError):
            apm.clone("nonexistent", "new")

    def test_clone_duplicate_name_raises(self, tmp_path):
        qname, defn = _make_agent_def("p", "a")
        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})
        # First clone succeeds
        apm.clone(qname, "cloned")
        # Second clone to the same name raises because the target file already exists
        import pytest
        with pytest.raises(ValueError):
            apm.clone(qname, "cloned")

    def test_cloned_profile_has_workspace_source(self, tmp_path):
        qname, defn = _make_agent_def("p", "a")
        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})
        apm.clone(qname, "cloned")
        assert apm.get("cloned").source == "workspace"


# ---------------------------------------------------------------------------
# TestReload
# ---------------------------------------------------------------------------


class TestReload:
    def test_reload_clears_old_profiles(self, tmp_path):
        qname1, defn1 = _make_agent_def("p", "old")
        apm = AgentProfileManager(tmp_path)
        apm.load({qname1: defn1})
        assert apm.get(qname1) is not None

        qname2, defn2 = _make_agent_def("p", "new")
        apm.reload({qname2: defn2})
        assert apm.get(qname2) is not None
        # old profile should no longer exist (no workspace yaml for it)
        assert apm.get(qname1) is None
