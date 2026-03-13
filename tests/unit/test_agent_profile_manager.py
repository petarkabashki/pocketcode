"""Unit tests for AgentProfileManager (T031).

Covers:
- Synthesised default profile generation from agent definitions
- Explicit namespace-declared default_agent_profile merging
- Workspace YAML file loading with correct precedence
- Collision handling (namespace > workspace > synthesised)
- Malformed YAML graceful handling
- get() / list() / clone() / save()
- reload() clears and re-populates the registry
"""

from __future__ import annotations

import yaml

from pocketcode.core.agent_profile_manager import AgentProfileManager
from pocketcode.core.namespace_registry import NamespaceRegistry
from pocketcode.core.runtime_models import AgentDefinition, AgentProfile


def _make_agent_def(
    namespace_name: str,
    agent_name: str,
    *,
    llm_profile: str | None = None,
    default_agent_profile: AgentProfile | None = None,
) -> tuple[str, AgentDefinition]:
    """Return (qualified_name, AgentDefinition) for test fixtures."""
    qname = f"{namespace_name}.{agent_name}"
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
        qname, defn = _make_agent_def("sample_namespace", "myagent")
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


class TestNamespaceDeclaredProfile:
    def test_namespace_declared_profile_wins_over_synthesised(self, tmp_path):
        qname, defn = _make_agent_def("p", "a")
        declared = AgentProfile(
            name="p.a:custom",
            flow=qname,
            llm_profile="gpt-4",
            source="namespace",
        )
        defn.default_agent_profile = declared

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        # Namespace-declared name must exist with the right LLM
        plug = apm.get("p.a:custom")
        assert plug is not None
        assert plug.llm_profile == "gpt-4"
        assert plug.source == "namespace"
        # No separate synthesised entry — the namespace declared its own explicit profile.
        assert apm.get(qname) is None

    def test_namespace_name_fallback_to_qualified(self, tmp_path):
        qname, defn = _make_agent_def("sample_namespace", "myagent")
        declared = AgentProfile(name=qname, flow=qname, source="namespace")
        defn.default_agent_profile = declared

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        profile = apm.get(qname)
        assert profile.source == "namespace"

    def test_namespace_local_agent_yaml_loads_without_copying_flow_defaults(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent", llm_profile="gemini_fast")
        defn.tools = ["tool.read", "tool.write"]
        namespace_root = tmp_path / "plug"
        namespace_root.mkdir(parents=True, exist_ok=True)
        (namespace_root / "agent.agent.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "plug.agent",
                    "flow": qname,
                    "description": "Namespace-local composite agent.",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        defn.metadata = {"namespace_root": str(namespace_root)}

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        profile = apm.get("plug.agent")
        assert profile is not None
        assert profile.source == "namespace"
        assert profile.flow == qname
        assert profile.llm_profile is None
        assert profile.tools is None

    def test_namespace_local_agent_yaml_uses_dotted_flow_reference(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        namespace_root = tmp_path / "plug"
        namespace_root.mkdir(parents=True, exist_ok=True)
        (namespace_root / "agent.agent.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "plug.agent",
                    "flow": qname,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        defn.metadata = {"namespace_root": str(namespace_root)}

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        profile = apm.get("plug.agent")
        assert profile is not None
        assert profile.flow == "plug.agent"

    def test_namespace_local_markdown_agent_resolves_prompt_imports_in_namespace_context(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        namespace_root = tmp_path / "plug"
        namespace_root.mkdir(parents=True, exist_ok=True)
        (namespace_root / "agent.agent.md").write_text(
            """---
name: plug.agent
flow: plug.agent
---
{{ import:prompt:review }}
""",
            encoding="utf-8",
        )
        defn.metadata = {"namespace_root": str(namespace_root), "namespace": "plug"}
        prompts = NamespaceRegistry()
        prompts.register("plug", "review", "Namespace-local imported prompt.")

        apm = AgentProfileManager(tmp_path, prompt_registry=prompts)
        apm.load({qname: defn})

        profile = apm.get("plug.agent")
        assert profile is not None
        assert profile.inline_prompt == "Namespace-local imported prompt."

    def test_namespace_agent_yaml_respects_ignore_rules(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        namespace_root = tmp_path / "plug"
        namespace_root.mkdir(parents=True, exist_ok=True)
        (tmp_path / ".pocketcodeignore").write_text("plug/*.agent.yaml\n!plug/keep.agent.yaml\n", encoding="utf-8")
        (namespace_root / "drop.agent.yaml").write_text(
            yaml.safe_dump({"name": "drop", "flow": qname}, sort_keys=False),
            encoding="utf-8",
        )
        (namespace_root / "keep.agent.yaml").write_text(
            yaml.safe_dump({"name": "keep", "flow": qname}, sort_keys=False),
            encoding="utf-8",
        )
        defn.metadata = {"namespace_root": str(namespace_root)}

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
        ws_profiles = tmp_path / ".pocketcode"
        self._write_ws_profile(
            ws_profiles,
            "custom.agent.yaml",
            {"name": "custom", "flow": qname},
        )
        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})
        assert apm.get("custom") is not None

    def test_workspace_profiles_load_from_additional_resource_root(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        ws_profiles = tmp_path / ".pocketflow"
        self._write_ws_profile(
            ws_profiles,
            "flow-review.agent.yaml",
            {"name": "flow-review", "flow": qname},
        )

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        assert apm.get("flow-review") is not None

    def test_workspace_markdown_agent_profile_loads_inline_prompt(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        profiles_dir = tmp_path / ".pocketcode"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        (profiles_dir / "review.agent.md").write_text(
            """---
name: review
flow: plug.agent
tools:
  - tool:core.read_file
---
Review only the changed files.
""",
            encoding="utf-8",
        )

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        profile = apm.get("review")
        assert profile is not None
        assert profile.flow == "plug.agent"
        assert profile.tools == ["core.read_file"]
        assert profile.inline_prompt == "Review only the changed files."

    def test_workspace_root_agent_convention_loads_agent_profile(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        source_path = tmp_path / ".pocketcode" / "review.agent.md"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(
            """---
name: review
flow: plug.agent
---
Review only the changed files.
""",
            encoding="utf-8",
        )

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        profile = apm.get("review")
        assert profile is not None
        assert profile.flow == "plug.agent"
        assert profile.inline_prompt == "Review only the changed files."
        assert profile.source_path == source_path.resolve()

    def test_workspace_agents_folder_loads_markdown_agent_profile(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        source_path = tmp_path / ".pocketcode" / "agents" / "review" / "safe.agent.md"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(
            """---
flow: plug.agent
---
Review only the changed files.
""",
            encoding="utf-8",
        )

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        profile = apm.get("review.safe")
        assert profile is not None
        assert profile.flow == "plug.agent"
        assert profile.inline_prompt == "Review only the changed files."
        assert profile.source_path == source_path.resolve()

    def test_workspace_typed_agent_folder_loads_markdown_agent_profile(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        source_path = tmp_path / ".pocketcode" / "agent.review" / "safe.agent.md"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(
            """---
flow: plug.agent
---
Review only the changed files.
""",
            encoding="utf-8",
        )

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        profile = apm.get("review.safe")
        assert profile is not None
        assert profile.flow == "plug.agent"
        assert profile.inline_prompt == "Review only the changed files."

    def test_workspace_markdown_agent_profile_resolves_prompt_imports(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        profiles_dir = tmp_path / ".pocketcode"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        (profiles_dir / "review.agent.md").write_text(
            """---
name: review
flow: plug.agent
---
{{ import:prompt:review }}
""",
            encoding="utf-8",
        )
        prompts = NamespaceRegistry()
        prompts.register("workspace", "review", "Imported workspace prompt.")

        apm = AgentProfileManager(tmp_path, prompt_registry=prompts)
        apm.load({qname: defn})

        profile = apm.get("review")
        assert profile is not None
        assert profile.inline_prompt == "Imported workspace prompt."


class TestInheritedAgents:
    def test_workspace_agent_can_extend_another_agent(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent", llm_profile="base-llm")
        defn.tools = ["tool.read"]
        profiles_dir = tmp_path / ".pocketcode"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        (profiles_dir / "base.agent.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "base",
                    "flow": qname,
                    "llm_profile": "review-llm",
                    "extra_prompts": ["prompts/base.md"],
                    "tools": ["tool.read"],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (profiles_dir / "child.agent.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "child",
                    "extends": "base",
                    "extra_prompts": ["prompts/child.md"],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        child = apm.resolve("child")
        assert child is not None
        assert child.flow == "plug.agent"
        assert child.base_agent == "base"
        assert child.llm_profile == "review-llm"
        assert child.tools == ["tool.read"]
        assert child.extra_prompts == ["prompts/base.md", "prompts/child.md"]

    def test_workspace_agent_command_aliases_inherit_with_child_override(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent", llm_profile="base-llm")
        profiles_dir = tmp_path / ".pocketcode"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        (profiles_dir / "base.agent.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "base",
                    "flow": qname,
                    "commands": [
                        {"name": "compact-now", "target": "memory compact 10"},
                        {"name": "checkpoint-list", "target": "checkpoint list"},
                    ],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (profiles_dir / "child.agent.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "child",
                    "extends": "base",
                    "commands": [
                        {"name": "compact-now", "target": "memory compact 1"},
                    ],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        child = apm.resolve("child")

        assert child is not None
        assert [(command.name, command.target) for command in child.commands] == [
            ("compact-now", "memory compact 1"),
            ("checkpoint-list", "checkpoint list"),
        ]

    def test_workspace_agent_extends_unknown_base_is_not_resolved(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        profiles_dir = tmp_path / ".pocketcode"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        (profiles_dir / "child.agent.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "child",
                    "extends": "missing",
                    "flow": qname,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        assert apm.get("child") is not None
        assert apm.resolve("child") is None


class TestWorkspaceYamlLoadingContinued(TestWorkspaceYamlLoading):
    def test_workspace_markdown_agent_profile_is_saved_as_markdown(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        profiles_dir = tmp_path / ".pocketcode"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        source_path = profiles_dir / "review.agent.md"
        source_path.write_text(
            """---
name: review
flow: plug.agent
---
Initial prompt.
""",
            encoding="utf-8",
        )

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        profile = apm.get("review")
        profile.inline_prompt = "Updated prompt."
        apm.save(profile)

        saved = source_path.read_text(encoding="utf-8")
        assert "Updated prompt." in saved
        assert "flow: plug.agent" in saved

    def test_workspace_yaml_loads_profile_skills(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        ws_profiles = tmp_path / ".pocketcode"
        self._write_ws_profile(
            ws_profiles,
            "custom.agent.yaml",
            {"name": "custom", "flow": qname, "skills": ["python-lint", "python-testing"]},
        )
        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        profile = apm.get("custom")
        assert profile is not None
        assert profile.skills == ["python-lint", "python-testing"]

    def test_workspace_profile_source_is_workspace(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        ws_profiles = tmp_path / ".pocketcode"
        self._write_ws_profile(ws_profiles, "ws.agent.yaml", {"name": "ws", "flow": qname})
        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        assert apm.get("ws").source == "workspace"

    def test_workspace_ignore_rules_skip_disabled_and_ignored_agent_files(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        (tmp_path / ".pocketcode").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".pocketcode" / ".pocketcodeignore").write_text(
            "\n".join(
                [
                    "*.agent.yaml",
                    "!keep.agent.yaml",
                ]
            ),
            encoding="utf-8",
        )
        ws_profiles = tmp_path / ".pocketcode"
        self._write_ws_profile(ws_profiles, "drop.agent.yaml", {"name": "drop", "flow": qname})
        self._write_ws_profile(ws_profiles, "keep.agent.yaml", {"name": "keep", "flow": qname})
        self._write_ws_profile(ws_profiles, "hidden.disabled.agent.yaml", {"name": "hidden", "flow": qname})

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        assert apm.get("drop") is None
        assert apm.get("keep") is not None
        assert apm.get("hidden") is None

    def test_invalid_typed_flow_reference_skips_workspace_profile(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        ws_profiles = tmp_path / ".pocketcode"
        self._write_ws_profile(
            ws_profiles,
            "bad.agent.yaml",
            {"name": "bad", "flow": "tool:core.read_file"},
        )

        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        assert apm.get("bad") is None

    def test_workspace_profile_loader_normalizes_typed_refs(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        ws_profiles = tmp_path / ".pocketcode"
        self._write_ws_profile(
            ws_profiles,
            "typed.agent.yaml",
            {
                "name": "typed",
                "flow": "flow:plug.agent",
                "tools": ["tool:core.read_file"],
                "extra_prompts": ["prompt:resource_root.pocketcode#review"],
            },
        )

        apm = AgentProfileManager(tmp_path)
        apm.load({"plug.agent": defn})

        profile = apm.get("typed")
        assert profile is not None
        assert profile.flow == "plug.agent"
        assert profile.tools == ["core.read_file"]
        assert profile.extra_prompts == ["prompt:resource_root.pocketcode.review"]

    def test_workspace_beats_synthesised_same_name(self, tmp_path):
        qname, defn = _make_agent_def("plug", "agent")
        ws_profiles = tmp_path / ".pocketcode"
        # workspace file claims the same name as the synthesised profile
        self._write_ws_profile(ws_profiles, "collision.agent.yaml", {"name": qname, "flow": qname, "llm_profile": "ws-llm"})
        apm = AgentProfileManager(tmp_path)
        apm.load({qname: defn})

        profile = apm.get(qname)
        assert profile.source == "workspace"
        assert profile.llm_profile == "ws-llm"

    def test_namespace_beats_workspace_same_name(self, tmp_path, caplog):
        qname, defn = _make_agent_def("plug", "agent")
        declared = AgentProfile(name="shared", flow=qname, llm_profile="namespace-llm", source="namespace")
        defn.default_agent_profile = declared

        ws_profiles = tmp_path / ".pocketcode"
        self._write_ws_profile(ws_profiles, "ws.agent.yaml", {"name": "shared", "flow": qname, "llm_profile": "ws-llm"})

        apm = AgentProfileManager(tmp_path)
        with caplog.at_level("WARNING"):
            apm.load({qname: defn})

        profile = apm.get("shared")
        assert profile.source == "namespace"
        assert profile.llm_profile == "namespace-llm"


# ---------------------------------------------------------------------------
# TestMalformedYaml
# ---------------------------------------------------------------------------


class TestMalformedYaml:
    def test_malformed_yaml_skipped_with_warning(self, tmp_path, caplog):
        ws_profiles = tmp_path / ".pocketcode"
        ws_profiles.mkdir(parents=True, exist_ok=True)
        bad = ws_profiles / "bad.agent.yaml"
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
        yaml_file = tmp_path / ".pocketcode" / "agent.cloned" / "cloned.agent.yaml"
        assert yaml_file.exists()

    def test_save_writes_profile_skills(self, tmp_path):
        profile = AgentProfile(
            name="cloned",
            flow="p.a",
            skills=["python-testing"],
            source="workspace",
            source_path=tmp_path / ".pocketcode" / "cloned.agent.yaml",
        )
        apm = AgentProfileManager(tmp_path)

        apm.save(profile)

        saved = yaml.safe_load(profile.source_path.read_text(encoding="utf-8"))
        assert saved["skills"] == ["python-testing"]

    def test_save_canonicalizes_persisted_reference_fields(self, tmp_path):
        profile = AgentProfile(
            name="cloned",
            flow="agent:coder.coder",
            extra_prompts=["prompt:resource_root.pocketcode.review", "prompts/base.md"],
            tools=["tool:filesystem.read_file", "search.web_search"],
            tool_confirmation={
                "default": "confirm",
                "overrides": {
                    "tool:filesystem.delete_file": "deny",
                    "search.web_search": "allow",
                },
            },
            source="workspace",
            source_path=tmp_path / ".pocketcode" / "cloned.agent.yaml",
        )
        apm = AgentProfileManager(tmp_path)

        apm.save(profile)

        saved = yaml.safe_load(profile.source_path.read_text(encoding="utf-8"))
        assert saved["flow"] == "coder.coder"
        assert saved["extra_prompts"] == ["prompt:resource_root.pocketcode.review", "prompts/base.md"]
        assert saved["tools"] == ["filesystem.read_file", "search.web_search"]
        assert saved["tool_confirmation"] == {
            "default": "confirm",
            "overrides": {
                "filesystem.delete_file": "deny",
                "search.web_search": "allow",
            },
        }

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


# ---------------------------------------------------------------------------
# TestSelfContainedMarkdownAgent
# ---------------------------------------------------------------------------


class TestSelfContainedMarkdownAgent:
    def test_self_contained_markdown_agent_registers_flow(self, tmp_path):
        profiles_dir = tmp_path / ".pocketcode"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        (profiles_dir / "hybrid.agent.md").write_text(
            """---
name: hybrid
vm_source: |
  [ "Hybrid ready." answer ] "main" define
vm_entry: main
---
Hybrid agent prompt.
""",
            encoding="utf-8",
        )

        apm = AgentProfileManager(tmp_path)
        apm.load({})

        # Agent should be registered
        profile = apm.get("hybrid")
        assert profile is not None
        assert profile.name == "hybrid"
        assert profile.flow == "agents.hybrid"
        assert profile.inline_prompt == "Hybrid agent prompt."

        # Flow should be registered in the manager's internal flow definitions
        flow_def = apm._flow_definitions.get("agents.hybrid")
        assert flow_def is not None
        assert flow_def.name == "agents.hybrid"
        assert flow_def.vm_source == '[ "Hybrid ready." answer ] "main" define'
        assert flow_def.vm_entry == "main"
        assert flow_def.execution_mode == "vm"

    def test_self_contained_markdown_agent_with_explicit_flow_name(self, tmp_path):
        profiles_dir = tmp_path / ".pocketcode"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        (profiles_dir / "hybrid.agent.md").write_text(
            """---
name: hybrid
flow: custom.flow
vm_source: |
  [ "Hybrid ready." answer ] "main" define
vm_entry: main
---
""",
            encoding="utf-8",
        )

        apm = AgentProfileManager(tmp_path)
        apm.load({})

        profile = apm.get("hybrid")
        assert profile is not None
        assert profile.flow == "custom.flow"

        flow_def = apm._flow_definitions.get("custom.flow")
        assert flow_def is not None
        assert flow_def.vm_source == '[ "Hybrid ready." answer ] "main" define'
