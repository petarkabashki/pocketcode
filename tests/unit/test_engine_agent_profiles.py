from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import yaml

from pocketcode.core.engine import PocketCodeEngine
from pocketcode.core.markdown_profiles import SkillDefinition
from pocketcode.core.namespace_registry import NamespaceRegistry
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
            flow=profile.flow,
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


class _SkillManagerStub:
    def __init__(self, skills: dict[str, SkillDefinition]):
        self._skills = skills

    def get(self, name: str):
        return self._skills.get(name)

    def list(self):
        return sorted(self._skills.values(), key=lambda skill: skill.name)


class _CatalogWithToolResolution:
    def __init__(self):
        self.agents = {"coder.coder": object()}
        self.resolve_call_count = 0

    def resolve_tools_for_agent(self, agent_name: str):
        self.resolve_call_count += 1
        return ["tool.b", "tool.a"]


class _CatalogWithQualifiedTools:
    def __init__(self):
        self.agents = {
            "coder.coder": type("Defn", (), {"metadata": {"namespace": "core"}, "default_agent_profile": None})()
        }
        self.tools = NamespaceRegistry()
        self.tools.register("core", "read_file", lambda **kw: {"ok": True})
        self.resolve_call_count = 0

    def resolve_tools_for_agent(self, agent_name: str):
        self.resolve_call_count += 1
        return ["core.read_file"]


class TestEngineAgentProfiles:
    def test_validate_loaded_agent_profiles_canonicalizes_refs_and_prunes_missing_targets(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        agents = NamespaceRegistry()
        agents.register(
            "coder",
            "coder",
            type("Defn", (), {"metadata": {"namespace": "core"}, "default_agent_profile": None})(),
        )
        tools = NamespaceRegistry()
        tools.register("core", "read_file", lambda **kw: {"ok": True})
        prompts = NamespaceRegistry()
        prompts.register("resource_root.pocketcode", "keep", "Keep prompt.")
        engine._catalog = type("Plugins", (), {"agents": agents, "tools": tools, "prompts": prompts})()
        engine._agent_profile_manager = _ProfileManagerStub(
            {
                "coder.safe": AgentProfile(
                    name="coder.safe",
                    flow="coder.coder",
                    tools=["read_file", "tool:missing.read_file"],
                    extra_prompts=[
                        "prompt:resource_root.pocketcode.keep",
                        "prompt:missing.keep",
                    ],
                )
            }
        )
        engine._skill_manager = _SkillManagerStub({})

        engine._validate_loaded_reference_surfaces()

        profile = engine._agent_profile_manager.get("coder.safe")
        assert profile is not None
        assert profile.flow == "coder.coder"
        assert profile.tools == ["core.read_file"]
        assert profile.extra_prompts == ["prompt:resource_root.pocketcode.keep"]

    def test_validate_loaded_skills_prunes_global_invalid_refs_and_keeps_contextual_unqualified_refs(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        agents = NamespaceRegistry()
        tools = NamespaceRegistry()
        tools.register("core", "read_file", lambda **kw: {"ok": True})
        prompts = NamespaceRegistry()
        prompts.register("resource_root.pocketcode", "keep", "Keep prompt.")
        engine._catalog = type("Plugins", (), {"agents": agents, "tools": tools, "prompts": prompts})()
        engine._agent_profile_manager = _ProfileManagerStub({})
        engine._skill_manager = _SkillManagerStub(
            {
                "python-testing": SkillDefinition(
                    name="python-testing",
                    tool_refs=["read_file", "tool:core.read_file", "tool:missing.read_file"],
                    extra_prompts=["prompt:review", "prompt:resource_root.pocketcode.keep", "prompt:missing.keep"],
                )
            }
        )

        engine._validate_loaded_reference_surfaces()

        skill = engine._skill_manager.get("python-testing")
        assert skill is not None
        assert skill.tool_refs == ["read_file", "core.read_file"]
        assert skill.extra_prompts == ["prompt:review", "prompt:resource_root.pocketcode.keep"]

    def test_get_system_settings_normalizes_old_default_agent(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._runtime_config = {"default_agent": "core.react", "textual": {}}
        engine._llm_config = {"default_profile": "fast"}
        registry = NamespaceRegistry()
        registry.register("core", "react", object())
        engine._catalog = type("Plugins", (), {"agents": registry})()

        settings = engine.get_system_settings()

        assert settings["default_agent"] == "core.react"

    def test_get_system_settings_normalizes_typed_default_agent(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._runtime_config = {"default_agent": "agent:core.react", "textual": {}}
        engine._llm_config = {"default_profile": "fast"}
        registry = NamespaceRegistry()
        registry.register("core", "react", object())
        engine._catalog = type("Plugins", (), {"agents": registry})()

        settings = engine.get_system_settings()

        assert settings["default_agent"] == "core.react"

    def test_set_active_agent_profile_switches_current_agent(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        profile = AgentProfile(name="coder.safe", flow="coder.coder", source="workspace")
        engine._agent_profile_manager = _ProfileManagerStub({"coder.safe": profile})
        engine._catalog = type("Plugins", (), {"agents": {"coder.coder": object()}})()
        engine.current_agent = None
        engine.active_agent_profile = None

        engine.set_active_agent_profile("coder.safe")

        assert engine.current_agent == "coder.coder"
        assert engine.active_agent_profile is profile

    def test_set_agent_accepts_typed_flow_reference(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        registry = NamespaceRegistry()
        registry.register("coder", "coder", type("Defn", (), {"default_agent_profile": None})())
        engine._catalog = type("Plugins", (), {"agents": registry})()
        engine._activate_default_profile_for = lambda agent_name: setattr(engine, "current_agent", agent_name)
        engine.current_agent = None
        engine.active_agent_profile = None
        engine.set_agent("flow:coder.coder")

        assert engine.current_agent == "coder.coder"

    def test_list_agent_profiles_accepts_typed_flow_filter(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        registry = NamespaceRegistry()
        registry.register("coder", "coder", object())
        registry.register("asker", "asker", object())
        engine._catalog = type("Plugins", (), {"agents": registry})()
        engine._agent_profile_manager = _ProfileManagerStub(
            {
                "coder.safe": AgentProfile(name="coder.safe", flow="coder.coder"),
                "asker.fast": AgentProfile(name="asker.fast", flow="asker.asker"),
            }
        )

        assert engine.list_agent_profiles("flow:coder.coder") == ["coder.safe"]

    def test_clone_markdown_tool_asset_rewrites_name_and_handler_path(self, tmp_path):
        tool_path = tmp_path / ".pocketcode" / "sample_tool.tool.md"
        tool_path.parent.mkdir(parents=True, exist_ok=True)
        tool_path.write_text(
            "---\nname: sample_tool\nhandler: ./sample_tool.tool.py:SampleTool\n---\nbody\n",
            encoding="utf-8",
        )
        handler_path = tmp_path / ".pocketcode" / "sample_tool.tool.py"
        handler_path.write_text("class SampleTool: pass\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        tool_registry = NamespaceRegistry()
        tool_registry.register("workspace", "sample_tool", SimpleNamespace(_tool_source_path=tool_path))
        engine._catalog = SimpleNamespace(tools=tool_registry, flows=NamespaceRegistry(), resource_roots=[])
        engine.reload_called = False
        engine.reload = lambda: setattr(engine, "reload_called", True)

        cloned = engine.clone_markdown_asset("tool", "sample_tool", "sample_tool_copy")

        cloned_markdown = cloned["path"].read_text(encoding="utf-8")
        cloned_handler = cloned["companion_path"].read_text(encoding="utf-8")
        assert cloned["path"].name == "sample_tool_copy.tool.md"
        assert cloned["companion_path"].name == "sample_tool_copy.tool.py"
        assert "name: sample_tool_copy" in cloned_markdown
        assert "handler: ./sample_tool_copy.tool.py:SampleTool" in cloned_markdown
        assert cloned_handler == "class SampleTool: pass\n"
        assert engine.reload_called is True

    def test_clone_markdown_tool_asset_cleans_up_when_cloned_handler_object_is_missing(self, tmp_path):
        tool_path = tmp_path / ".pocketcode" / "sample_tool.tool.md"
        tool_path.parent.mkdir(parents=True, exist_ok=True)
        tool_path.write_text(
            "---\nname: sample_tool\nhandler: ./sample_tool.tool.py:SampleTool\n---\nbody\n",
            encoding="utf-8",
        )
        handler_path = tmp_path / ".pocketcode" / "sample_tool.tool.py"
        handler_path.write_text("class DifferentTool: pass\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        tool_registry = NamespaceRegistry()
        tool_registry.register("workspace", "sample_tool", SimpleNamespace(_tool_source_path=tool_path))
        engine._catalog = SimpleNamespace(tools=tool_registry, flows=NamespaceRegistry(), resource_roots=[])
        engine.reload_called = False
        engine.reload = lambda: setattr(engine, "reload_called", True)

        try:
            engine.clone_markdown_asset("tool", "sample_tool", "sample_tool_copy")
        except ValueError as exc:
            assert "Tool handler 'SampleTool' was not found in" in str(exc)
        else:
            raise AssertionError("Expected ValueError for missing cloned tool handler object.")

        assert not (tmp_path / ".pocketcode" / "sample_tool_copy.tool.md").exists()
        assert not (tmp_path / ".pocketcode" / "sample_tool_copy.tool.py").exists()
        assert engine.reload_called is False

    def test_clone_markdown_tool_asset_rejects_invalid_import_path_handler(self, tmp_path):
        tool_path = tmp_path / ".pocketcode" / "sample_tool.tool.md"
        tool_path.parent.mkdir(parents=True, exist_ok=True)
        tool_path.write_text(
            "---\nname: sample_tool\nhandler: missing.module.SampleTool\n---\nbody\n",
            encoding="utf-8",
        )

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        tool_registry = NamespaceRegistry()
        tool_registry.register("workspace", "sample_tool", SimpleNamespace(_tool_source_path=tool_path))
        engine._catalog = SimpleNamespace(tools=tool_registry, flows=NamespaceRegistry(), resource_roots=[])
        engine.reload_called = False
        engine.reload = lambda: setattr(engine, "reload_called", True)

        try:
            engine.clone_markdown_asset("tool", "sample_tool", "sample_tool_copy")
        except ValueError as exc:
            assert "Tool handler module import failed for 'missing.module'" in str(exc)
        else:
            raise AssertionError("Expected ValueError for invalid import-path handler during clone.")

        assert not (tmp_path / ".pocketcode" / "sample_tool_copy.tool.md").exists()
        assert not (tmp_path / ".pocketcode" / "sample_tool_copy.tool.py").exists()
        assert engine.reload_called is False

    def test_clone_markdown_tool_asset_rejects_missing_prompt_include_and_cleans_up(self, tmp_path):
        tool_path = tmp_path / ".pocketcode" / "sample_tool.tool.md"
        tool_path.parent.mkdir(parents=True, exist_ok=True)
        tool_path.write_text(
            "---\nname: sample_tool\nhandler: ./sample_tool.tool.py:SampleTool\n---\n{{ include:missing-prompt.md }}\n",
            encoding="utf-8",
        )
        handler_path = tmp_path / ".pocketcode" / "sample_tool.tool.py"
        handler_path.write_text("class SampleTool: pass\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        tool_registry = NamespaceRegistry()
        tool_registry.register("workspace", "sample_tool", SimpleNamespace(_tool_source_path=tool_path))
        engine._catalog = SimpleNamespace(
            tools=tool_registry,
            flows=NamespaceRegistry(),
            prompts=NamespaceRegistry(),
            resource_roots=[],
        )
        engine.reload_called = False
        engine.reload = lambda: setattr(engine, "reload_called", True)

        try:
            engine.clone_markdown_asset("tool", "sample_tool", "sample_tool_copy")
        except FileNotFoundError as exc:
            assert "Prompt file not found" in str(exc)
        else:
            raise AssertionError("Expected FileNotFoundError for missing included prompt file during clone.")

        assert not (tmp_path / ".pocketcode" / "sample_tool_copy.tool.md").exists()
        assert not (tmp_path / ".pocketcode" / "sample_tool_copy.tool.py").exists()
        assert engine.reload_called is False

    def test_update_markdown_asset_rejects_mismatched_front_matter_name(self, tmp_path):
        flow_path = tmp_path / ".pocketcode" / "sample_flow.md"
        flow_path.parent.mkdir(parents=True, exist_ok=True)
        flow_path.write_text("---\nname: sample_flow\n---\nbody\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        flow_registry = NamespaceRegistry()
        flow_registry.register(
            "workspace",
            "sample_flow",
            SimpleNamespace(name="sample_flow", metadata={"markdown_path": str(flow_path)}),
        )
        engine._catalog = SimpleNamespace(tools=NamespaceRegistry(), flows=flow_registry, resource_roots=[])
        engine.reload = lambda: None

        try:
            engine.update_markdown_asset(
                "flow",
                "sample_flow",
                markdown_text="---\nname: other_flow\n---\nbody\n",
            )
        except ValueError as exc:
            assert "does not match target flow 'sample_flow'" in str(exc)
        else:
            raise AssertionError("Expected ValueError for mismatched front matter name.")

    def test_update_markdown_flow_asset_accepts_old_graph_metadata_without_validation(self, tmp_path):
        flow_path = tmp_path / ".pocketcode" / "sample_flow.md"
        flow_path.parent.mkdir(parents=True, exist_ok=True)
        flow_path.write_text("---\nname: sample_flow\n---\nbody\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        flow_registry = NamespaceRegistry()
        flow_registry.register(
            "workspace",
            "sample_flow",
            SimpleNamespace(name="sample_flow", metadata={"markdown_path": str(flow_path)}),
        )
        engine._catalog = SimpleNamespace(tools=NamespaceRegistry(), flows=flow_registry, resource_roots=[])
        engine.reload = lambda: None

        engine.update_markdown_asset(
            "flow",
            "sample_flow",
            markdown_text=(
                "---\nname: sample_flow\nnodes:\n  start:\n    kind: noop\n    transition: missing\n  done:\n    kind: output\n    message: Done\n---\n```mermaid\ngraph TD\n  start -->|ok| done\n```\n"
            ),
        )

        saved_text = flow_path.read_text(encoding="utf-8")
        assert "transition: missing" in saved_text
        assert "graph TD" in saved_text

    def test_update_markdown_flow_asset_rejects_missing_prompt_include(self, tmp_path):
        flow_path = tmp_path / ".pocketcode" / "sample_flow.md"
        flow_path.parent.mkdir(parents=True, exist_ok=True)
        flow_path.write_text("---\nname: sample_flow\n---\nbody\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        flow_registry = NamespaceRegistry()
        flow_registry.register(
            "workspace",
            "sample_flow",
            SimpleNamespace(name="sample_flow", metadata={"markdown_path": str(flow_path)}),
        )
        engine._catalog = SimpleNamespace(
            tools=NamespaceRegistry(),
            flows=flow_registry,
            prompts=NamespaceRegistry(),
            resource_roots=[],
        )
        engine.reload = lambda: None

        try:
            engine.update_markdown_asset(
                "flow",
                "sample_flow",
                markdown_text="---\nname: sample_flow\n---\n{{ include:missing-prompt.md }}\n",
            )
        except FileNotFoundError as exc:
            assert "Prompt file not found" in str(exc)
        else:
            raise AssertionError("Expected FileNotFoundError for missing included prompt file.")

    def test_update_markdown_flow_asset_rejects_missing_tool_reference(self, tmp_path):
        flow_path = tmp_path / ".pocketcode" / "sample_flow.md"
        flow_path.parent.mkdir(parents=True, exist_ok=True)
        flow_path.write_text("---\nname: sample_flow\n---\nbody\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        flow_registry = NamespaceRegistry()
        flow_registry.register(
            "workspace",
            "sample_flow",
            SimpleNamespace(name="sample_flow", metadata={"markdown_path": str(flow_path)}),
        )
        engine._catalog = SimpleNamespace(tools=NamespaceRegistry(), flows=flow_registry, prompts=NamespaceRegistry(), resource_roots=[])
        engine.reload = lambda: None

        try:
            engine.update_markdown_asset(
                "flow",
                "sample_flow",
                markdown_text="---\nname: sample_flow\ntools:\n  - resource_root.pocketcode.missing_tool\n---\nbody\n",
            )
        except ValueError as exc:
            assert "sample_flow.md: tools[0] could not be resolved" in str(exc)
        else:
            raise AssertionError("Expected ValueError for missing flow tool reference.")

    def test_update_markdown_flow_asset_rejects_missing_handoff_target(self, tmp_path):
        flow_path = tmp_path / ".pocketcode" / "sample_flow.md"
        flow_path.parent.mkdir(parents=True, exist_ok=True)
        flow_path.write_text("---\nname: sample_flow\n---\nbody\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        flow_registry = NamespaceRegistry()
        flow_registry.register(
            "workspace",
            "sample_flow",
            SimpleNamespace(name="sample_flow", metadata={"markdown_path": str(flow_path)}),
        )
        engine._catalog = SimpleNamespace(tools=NamespaceRegistry(), flows=flow_registry, prompts=NamespaceRegistry(), resource_roots=[])
        engine.reload = lambda: None

        try:
            engine.update_markdown_asset(
                "flow",
                "sample_flow",
                markdown_text="---\nname: sample_flow\nhandoff_agents:\n  - resource_root.pocketcode.missing_flow\n---\nbody\n",
            )
        except ValueError as exc:
            assert "sample_flow.md: handoff_agents[0] could not be resolved" in str(exc)
        else:
            raise AssertionError("Expected ValueError for missing handoff flow reference.")

    def test_update_markdown_flow_asset_rejects_missing_prompt_bundle_reference(self, tmp_path):
        flow_path = tmp_path / ".pocketcode" / "flows" / "sample_flow.md"
        flow_path.parent.mkdir(parents=True, exist_ok=True)
        flow_path.write_text("---\nname: sample_flow\n---\nbody\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        flow_registry = NamespaceRegistry()
        flow_registry.register(
            "workspace",
            "sample_flow",
            SimpleNamespace(name="sample_flow", metadata={"markdown_path": str(flow_path)}),
        )
        engine._catalog = SimpleNamespace(tools=NamespaceRegistry(), flows=flow_registry, prompts=NamespaceRegistry(), resource_roots=[])
        engine.reload = lambda: None

        try:
            engine.update_markdown_asset(
                "flow",
                "sample_flow",
                markdown_text="---\nname: sample_flow\nprompt_files:\n  - prompt:missing.review\n---\nbody\n",
            )
        except Exception as exc:  # noqa: BLE001
            assert "missing.review" in str(exc)
        else:
            raise AssertionError("Expected failure for missing prompt bundle reference.")

    def test_update_markdown_agent_asset_rejects_missing_prompt_include(self, tmp_path):
        agent_path = tmp_path / ".pocketcode" / "review.agent.md"
        agent_path.parent.mkdir(parents=True, exist_ok=True)
        agent_path.write_text("---\nname: review\nflow: plug.agent\n---\nbody\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        engine._agent_profile_manager = _ProfileManagerStub(
            {
                "review": AgentProfile(name="review", flow="plug.agent", source="workspace", source_path=agent_path),
            }
        )
        flow_registry = NamespaceRegistry()
        flow_registry.register("plug", "agent", SimpleNamespace(name="plug.agent"))
        engine._catalog = SimpleNamespace(
            tools=NamespaceRegistry(),
            flows=flow_registry,
            prompts=NamespaceRegistry(),
            resource_roots=[],
        )
        engine.reload = lambda: None

        try:
            engine.update_markdown_asset(
                "agent",
                "review",
                markdown_text="---\nname: review\nflow: plug.agent\n---\n{{ include:missing-prompt.md }}\n",
            )
        except FileNotFoundError as exc:
            assert "Prompt file not found" in str(exc)
        else:
            raise AssertionError("Expected FileNotFoundError for missing included prompt file in agent asset.")

    def test_update_markdown_agent_asset_rejects_missing_target_flow(self, tmp_path):
        agent_path = tmp_path / ".pocketcode" / "review.agent.md"
        agent_path.parent.mkdir(parents=True, exist_ok=True)
        agent_path.write_text("---\nname: review\nflow: plug.agent\n---\nbody\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        engine._agent_profile_manager = _ProfileManagerStub(
            {"review": AgentProfile(name="review", flow="plug.agent", source="workspace", source_path=agent_path)}
        )
        engine._catalog = SimpleNamespace(
            tools=NamespaceRegistry(),
            flows=NamespaceRegistry(),
            prompts=NamespaceRegistry(),
            resource_roots=[],
        )
        engine.reload = lambda: None

        try:
            engine.update_markdown_asset(
                "agent",
                "review",
                markdown_text="---\nname: review\nflow: plug.agent\n---\nbody\n",
            )
        except ValueError as exc:
            assert "review.agent.md: flow could not be resolved" in str(exc)
        else:
            raise AssertionError("Expected ValueError for missing target flow.")

    def test_update_markdown_agent_asset_rejects_missing_tool_reference(self, tmp_path):
        agent_path = tmp_path / ".pocketcode" / "review.agent.md"
        agent_path.parent.mkdir(parents=True, exist_ok=True)
        agent_path.write_text("---\nname: review\nflow: plug.agent\n---\nbody\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        engine._agent_profile_manager = _ProfileManagerStub(
            {"review": AgentProfile(name="review", flow="plug.agent", source="workspace", source_path=agent_path)}
        )
        flow_registry = NamespaceRegistry()
        flow_registry.register("plug", "agent", SimpleNamespace(name="plug.agent"))
        engine._catalog = SimpleNamespace(
            tools=NamespaceRegistry(),
            flows=flow_registry,
            prompts=NamespaceRegistry(),
            resource_roots=[],
        )
        engine.reload = lambda: None

        try:
            engine.update_markdown_asset(
                "agent",
                "review",
                markdown_text="---\nname: review\nflow: plug.agent\ntools:\n  - resource_root.pocketcode.missing_tool\n---\nbody\n",
            )
        except ValueError as exc:
            assert "review.agent.md: tools[0] could not be resolved" in str(exc)
        else:
            raise AssertionError("Expected ValueError for missing tool reference.")

    def test_update_markdown_agent_asset_rejects_missing_prompt_resource(self, tmp_path):
        agent_path = tmp_path / ".pocketcode" / "review.agent.md"
        agent_path.parent.mkdir(parents=True, exist_ok=True)
        agent_path.write_text("---\nname: review\nflow: plug.agent\n---\nbody\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        engine._agent_profile_manager = _ProfileManagerStub(
            {"review": AgentProfile(name="review", flow="plug.agent", source="workspace", source_path=agent_path)}
        )
        flow_registry = NamespaceRegistry()
        flow_registry.register("plug", "agent", SimpleNamespace(name="plug.agent"))
        engine._catalog = SimpleNamespace(
            tools=NamespaceRegistry(),
            flows=flow_registry,
            prompts=NamespaceRegistry(),
            resource_roots=[],
        )
        engine.reload = lambda: None

        try:
            engine.update_markdown_asset(
                "agent",
                "review",
                markdown_text=(
                    "---\nname: review\nflow: plug.agent\nextra_prompts:\n  - prompt:missing.review\n---\nbody\n"
                ),
            )
        except ValueError as exc:
            assert "review.agent.md: extra_prompts[0] could not be resolved" in str(exc)
        else:
            raise AssertionError("Expected ValueError for missing prompt resource.")

    def test_clone_markdown_flow_asset_preserves_old_graph_metadata(self, tmp_path):
        flow_path = tmp_path / ".pocketcode" / "sample_flow.md"
        flow_path.parent.mkdir(parents=True, exist_ok=True)
        flow_path.write_text(
            "---\nname: sample_flow\nnodes:\n  start:\n    kind: noop\n    transition: missing\n  done:\n    kind: output\n    message: Done\n---\n```mermaid\ngraph TD\n  start -->|ok| done\n```\n",
            encoding="utf-8",
        )

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        flow_registry = NamespaceRegistry()
        flow_registry.register(
            "workspace",
            "sample_flow",
            SimpleNamespace(name="sample_flow", metadata={"markdown_path": str(flow_path)}),
        )
        engine._catalog = SimpleNamespace(tools=NamespaceRegistry(), flows=flow_registry, resource_roots=[])
        engine.reload_called = False
        engine.reload = lambda: setattr(engine, "reload_called", True)

        cloned = engine.clone_markdown_asset("flow", "sample_flow", "sample_flow_copy")

        cloned_path = tmp_path / ".pocketcode" / "sample_flow_copy.md"
        assert cloned["path"] == cloned_path
        assert cloned_path.exists()
        cloned_text = cloned_path.read_text(encoding="utf-8")
        assert "transition: missing" in cloned_text
        assert "graph TD" in cloned_text
        assert engine.reload_called is True

    def test_clone_markdown_agent_asset_rejects_missing_prompt_include_and_cleans_up(self, tmp_path):
        agent_path = tmp_path / ".pocketcode" / "review.agent.md"
        agent_path.parent.mkdir(parents=True, exist_ok=True)
        agent_path.write_text(
            "---\nname: review\nflow: plug.agent\n---\n{{ include:missing-prompt.md }}\n",
            encoding="utf-8",
        )

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        engine._agent_profile_manager = _ProfileManagerStub(
            {
                "review": AgentProfile(name="review", flow="plug.agent", source="workspace", source_path=agent_path),
            }
        )
        flow_registry = NamespaceRegistry()
        flow_registry.register("plug", "agent", SimpleNamespace(name="plug.agent"))
        engine._catalog = SimpleNamespace(
            tools=NamespaceRegistry(),
            flows=flow_registry,
            prompts=NamespaceRegistry(),
            resource_roots=[],
        )
        engine.reload_called = False
        engine.reload = lambda: setattr(engine, "reload_called", True)

        try:
            engine.clone_markdown_asset("agent", "review", "review_copy")
        except FileNotFoundError as exc:
            assert "Prompt file not found" in str(exc)
        else:
            raise AssertionError("Expected FileNotFoundError for missing included prompt file during agent clone.")

        assert not (tmp_path / ".pocketcode" / "agent.review_copy" / "review_copy.agent.md").exists()
        assert engine.reload_called is False

    def test_update_markdown_tool_asset_rejects_missing_handler_file(self, tmp_path):
        tool_path = tmp_path / ".pocketcode" / "sample_tool.tool.md"
        tool_path.parent.mkdir(parents=True, exist_ok=True)
        tool_path.write_text("---\nname: sample_tool\n---\nbody\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        tool_registry = NamespaceRegistry()
        tool_registry.register("workspace", "sample_tool", SimpleNamespace(_tool_source_path=tool_path))
        engine._catalog = SimpleNamespace(tools=tool_registry, flows=NamespaceRegistry(), resource_roots=[])
        engine.reload = lambda: None

        try:
            engine.update_markdown_asset(
                "tool",
                "sample_tool",
                markdown_text=(
                    "---\nname: sample_tool\nhandler: ./missing_tool.tool.py:SampleTool\n---\nbody\n"
                ),
            )
        except ValueError as exc:
            assert "Tool handler file not found" in str(exc)
        else:
            raise AssertionError("Expected ValueError for missing tool handler file.")

    def test_update_markdown_tool_asset_rejects_missing_handler_object(self, tmp_path):
        tool_path = tmp_path / ".pocketcode" / "sample_tool.tool.md"
        tool_path.parent.mkdir(parents=True, exist_ok=True)
        tool_path.write_text("---\nname: sample_tool\n---\nbody\n", encoding="utf-8")
        handler_path = tmp_path / ".pocketcode" / "sample_tool.tool.py"
        handler_path.write_text("class DifferentTool: pass\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        tool_registry = NamespaceRegistry()
        tool_registry.register("workspace", "sample_tool", SimpleNamespace(_tool_source_path=tool_path))
        engine._catalog = SimpleNamespace(tools=tool_registry, flows=NamespaceRegistry(), resource_roots=[])
        engine.reload = lambda: None

        try:
            engine.update_markdown_asset(
                "tool",
                "sample_tool",
                markdown_text=(
                    "---\nname: sample_tool\nhandler: ./sample_tool.tool.py:SampleTool\n---\nbody\n"
                ),
            )
        except ValueError as exc:
            assert "Tool handler 'SampleTool' was not found in" in str(exc)
        else:
            raise AssertionError("Expected ValueError for missing tool handler object.")

    def test_update_markdown_tool_asset_rejects_invalid_import_path_handler(self, tmp_path):
        tool_path = tmp_path / ".pocketcode" / "sample_tool.tool.md"
        tool_path.parent.mkdir(parents=True, exist_ok=True)
        tool_path.write_text("---\nname: sample_tool\n---\nbody\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        tool_registry = NamespaceRegistry()
        tool_registry.register("workspace", "sample_tool", SimpleNamespace(_tool_source_path=tool_path))
        engine._catalog = SimpleNamespace(tools=tool_registry, flows=NamespaceRegistry(), resource_roots=[])
        engine.reload = lambda: None

        try:
            engine.update_markdown_asset(
                "tool",
                "sample_tool",
                markdown_text=(
                    "---\nname: sample_tool\nhandler: missing.module.SampleTool\n---\nbody\n"
                ),
            )
        except ValueError as exc:
            assert "Tool handler module import failed for 'missing.module'" in str(exc)
        else:
            raise AssertionError("Expected ValueError for invalid import-path handler.")

    def test_delete_markdown_tool_asset_removes_markdown_and_keeps_handler(self, tmp_path):
        tool_path = tmp_path / ".pocketcode" / "sample_tool.tool.md"
        tool_path.parent.mkdir(parents=True, exist_ok=True)
        tool_path.write_text("---\nname: sample_tool\n---\nbody\n", encoding="utf-8")
        handler_path = tmp_path / ".pocketcode" / "sample_tool.tool.py"
        handler_path.write_text("class SampleTool: pass\n", encoding="utf-8")

        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        tool_registry = NamespaceRegistry()
        tool_registry.register("workspace", "sample_tool", SimpleNamespace(_tool_source_path=tool_path))
        engine._catalog = SimpleNamespace(tools=tool_registry, flows=NamespaceRegistry(), resource_roots=[])
        engine.reload_called = False
        engine.reload = lambda: setattr(engine, "reload_called", True)

        deleted = engine.delete_markdown_asset("tool", "sample_tool")

        assert deleted["path"] == tool_path.resolve()
        assert deleted["companion_path"] == handler_path.resolve()
        assert deleted["companion_deleted"] is False
        assert not tool_path.exists()
        assert handler_path.exists()
        assert engine.reload_called is True

    def test_set_active_agent_profile_rejects_unknown_target_agent(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        profile = AgentProfile(name="ghost.safe", flow="ghost.ghost", source="workspace")
        engine._agent_profile_manager = _ProfileManagerStub({"ghost.safe": profile})
        engine._catalog = type("Plugins", (), {"agents": {}})()
        engine.current_agent = None
        engine.active_agent_profile = None

        try:
            engine.set_active_agent_profile("ghost.safe")
        except ValueError as exc:
            assert "unknown agent" in str(exc).lower()
        else:
            raise AssertionError("Expected ValueError for profile targeting an unknown agent")

    def test_status_exposes_selected_flow_agent_and_llm(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine.current_agent = "coder.coder"
        engine.active_agent_profile = AgentProfile(
            name="coder.safe",
            flow="coder.coder",
            llm_profile="smart",
        )
        engine.enabled_skills = []
        engine._runtime_config = {"agent_runtime_workflow": "internal-flow"}
        engine.global_llm_override = "fast"
        engine.agent_llm_overrides = {}
        engine.handoff_llm_overrides = {}
        engine.config_llm_overrides = {}
        engine.default_llm_profile = "default"
        engine._tool_confirmation_config = {}
        engine.last_run_summary = {}
        engine._copy_session_confirmation_overrides = lambda: {}
        engine.list_flows = lambda: ["coder.coder"]
        engine.list_available_agents = lambda: ["coder.safe"]
        engine.list_skills = lambda: []
        engine.list_llm_profiles = lambda: ["default", "fast", "smart"]

        status = engine.status()

        assert status["selected_flow"] == "coder.coder"
        assert status["selected_agent"] == "coder.safe"
        assert status["selected_llm_profile"] == "smart"

    def test_list_agent_profiles_can_filter_by_agent(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._agent_profile_manager = _ProfileManagerStub(
            {
                "coder.safe": AgentProfile(name="coder.safe", flow="coder.coder"),
                "asker.fast": AgentProfile(name="asker.fast", flow="asker.asker"),
            }
        )

        assert engine.list_agent_profiles("coder.coder") == ["coder.safe"]
        assert engine.list_agent_profiles() == ["asker.fast", "coder.safe"]

    def test_update_agent_profile_persists_workspace_profile(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        profile = AgentProfile(
            name="coder.safe",
            flow="coder.coder",
            llm_profile=None,
            extra_prompts=["prompts/base.md"],
            tools=["filesystem.read_file"],
            tool_confirmation={"overrides": {"filesystem.delete_file": "deny"}},
            source="workspace",
            source_path=Path("/tmp/coder.safe.yaml"),
        )
        manager = _EditableProfileManagerStub({"coder.safe": profile})
        engine._agent_profile_manager = manager
        engine._catalog = type("Plugins", (), {"agents": {"coder.coder": object()}})()
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
            tools=["filesystem.read_file", "search.web_search"],
            extra_prompts=["prompts/base.md", "prompts/review.md"],
            tool_confirmation_default="confirm",
        )

        assert manager.saved_profile is not None
        assert manager.saved_profile.llm_profile == "gemini_fast"
        assert manager.saved_profile.skills is None
        assert manager.saved_profile.tools == ["filesystem.read_file", "search.web_search"]
        assert manager.saved_profile.extra_prompts == ["prompts/base.md", "prompts/review.md"]
        assert manager.saved_profile.tool_confirmation == {
            "default": "confirm",
            "overrides": {"filesystem.delete_file": "deny"},
        }
        assert manager.reload_count == 1
        assert updated is manager.saved_profile
        assert engine.active_agent_profile is manager.saved_profile

    def test_update_agent_profile_replaces_tool_confirmation_overrides_when_provided(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        profile = AgentProfile(
            name="coder.safe",
            flow="coder.coder",
            llm_profile=None,
            extra_prompts=[],
            tools=["filesystem.read_file"],
            tool_confirmation={"default": "confirm", "overrides": {"filesystem.delete_file": "deny"}},
            source="workspace",
            source_path=Path("/tmp/coder.safe.yaml"),
        )
        manager = _EditableProfileManagerStub({"coder.safe": profile})
        engine._agent_profile_manager = manager
        engine._catalog = type("Plugins", (), {"agents": {"coder.coder": object()}})()
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

        engine.update_agent_profile(
            "coder.safe",
            llm_profile=None,
            tools=["filesystem.read_file"],
            extra_prompts=[],
            tool_confirmation_default="confirm",
            tool_confirmation_overrides={
                "filesystem.delete_file": "allow",
                "search.web_search": "deny",
            },
        )

        assert manager.saved_profile is not None
        assert manager.saved_profile.tool_confirmation == {
            "default": "confirm",
            "overrides": {
                "filesystem.delete_file": "allow",
                "search.web_search": "deny",
            },
        }

    def test_replace_session_confirmation_overrides_canonicalizes_persisted_keys(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine.session_confirmation_overrides = {
            "default_policy": None,
            "tool_policies": {},
            "agent_policies": {},
        }
        engine._normalize_confirmation_policy = PocketCodeEngine._normalize_confirmation_policy.__get__(
            engine,
            PocketCodeEngine,
        )
        engine._normalize_tool_key_for_persistence = PocketCodeEngine._normalize_tool_key_for_persistence.__get__(
            engine,
            PocketCodeEngine,
        )
        engine._normalize_agent_key_for_persistence = PocketCodeEngine._normalize_agent_key_for_persistence.__get__(
            engine,
            PocketCodeEngine,
        )
        engine._normalize_session_confirmation_overrides = (
            PocketCodeEngine._normalize_session_confirmation_overrides.__get__(
                engine,
                PocketCodeEngine,
            )
        )
        engine._update_active_session_snapshot = lambda *args, **kwargs: None

        engine.replace_session_confirmation_overrides(
            {
                "default_policy": "confirm",
                "tool_policies": {
                    "tool:filesystem.delete_file": "deny",
                    "search.web_search": "allow",
                },
                "agent_policies": {
                    "agent:coder.coder": {
                        "default_policy": "allow",
                        "tool_policies": {
                            "tool:filesystem.read_file": "confirm",
                        },
                    }
                },
            }
        )

        assert engine.session_confirmation_overrides == {
            "default_policy": "confirm",
            "tool_policies": {
                "filesystem.delete_file": "deny",
                "search.web_search": "allow",
            },
            "agent_policies": {
                "coder.coder": {
                    "default_policy": "allow",
                    "tool_policies": {
                        "filesystem.read_file": "confirm",
                    },
                }
            },
        }

    def test_set_persistent_tool_confirmation_writes_canonical_tool_key(self, tmp_path):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        engine._config = {"runtime": {}}
        engine._runtime_config = engine._config["runtime"]
        engine._tool_confirmation_config = {}
        engine._normalize_confirmation_policy = PocketCodeEngine._normalize_confirmation_policy.__get__(
            engine,
            PocketCodeEngine,
        )
        engine._normalize_tool_key_for_persistence = PocketCodeEngine._normalize_tool_key_for_persistence.__get__(
            engine,
            PocketCodeEngine,
        )
        engine._set_policy_entry = PocketCodeEngine._set_policy_entry.__get__(engine, PocketCodeEngine)
        engine._build_tool_confirmation_config = PocketCodeEngine._build_tool_confirmation_config.__get__(
            engine,
            PocketCodeEngine,
        )
        engine._refresh_runtime_components = lambda: None
        engine._write_workspace_config = PocketCodeEngine._write_workspace_config.__get__(engine, PocketCodeEngine)

        engine.set_persistent_tool_confirmation("tool:filesystem.delete_file", "deny")

        saved = yaml.safe_load((tmp_path / "pocketcode.yml").read_text(encoding="utf-8"))
        assert saved["runtime"]["tool_confirmation"]["tool_policies"] == {
            "filesystem.delete_file": "deny"
        }

    def test_save_agent_profile_skills_persists_workspace_profile_and_clears_matching_override(self, tmp_path):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        profile = AgentProfile(
            name="coder.safe",
            flow="coder.coder",
            skills=["python-lint"],
            tools=["filesystem.read_file"],
            source="workspace",
            source_path=tmp_path / ".pocketcode" / "agents" / "coder.safe.yaml",
        )
        manager = _EditableProfileManagerStub({"coder.safe": profile})
        engine._agent_profile_manager = manager
        engine._catalog = type("Plugins", (), {"agents": {"coder.coder": object()}})()
        engine._llm_router = type(
            "Router",
            (),
            {"resolve_profile_config": staticmethod(lambda name: {"profile_name": name})},
        )()
        engine._skill_manager = _SkillManagerStub(
            {
                "python-lint": SkillDefinition(name="python-lint"),
                "python-testing": SkillDefinition(name="python-testing"),
            }
        )
        engine._config = {
            "runtime": {
                "textual": {
                    "last_used": {
                        "agent_profiles": {
                            "coder.safe": {
                                "skills": ["python-testing"],
                            }
                        }
                    }
                }
            }
        }
        engine._workspace_root = tmp_path
        engine.active_agent_profile = profile
        engine.enabled_skills = ["python-testing"]
        engine._normalize_confirmation_policy = PocketCodeEngine._normalize_confirmation_policy.__get__(
            engine,
            PocketCodeEngine,
        )
        engine._refresh_runtime_components = lambda: None
        engine._runtime_config = {}
        engine._tool_confirmation_config = {}
        engine._maybe_refresh_runtime_components = lambda: None

        refreshed = engine.save_agent_profile_skills("coder.safe", ["python-testing"])

        assert refreshed is manager.saved_profile
        assert manager.saved_profile is not None
        assert manager.saved_profile.skills == ["python-testing"]
        textual = engine._config["runtime"]["textual"]
        assert textual["last_used"]["agent_profiles"]["coder.safe"]["skills"] == ["python-testing"]

    def test_save_agent_profile_tools_persists_workspace_profile_and_clears_matching_override(self, tmp_path):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        profile = AgentProfile(
            name="coder.safe",
            flow="coder.coder",
            tools=None,
            source="workspace",
            source_path=tmp_path / ".pocketcode" / "agents" / "coder.safe.yaml",
        )
        manager = _EditableProfileManagerStub({"coder.safe": profile})
        engine._agent_profile_manager = manager
        engine._catalog = type("Plugins", (), {"agents": {"coder.coder": object()}})()
        engine._llm_router = type(
            "Router",
            (),
            {"resolve_profile_config": staticmethod(lambda name: {"profile_name": name})},
        )()
        engine._skill_manager = _SkillManagerStub({})
        engine._config = {
            "runtime": {
                "textual": {
                    "last_used": {
                        "agent_profiles": {
                            "coder.safe": {
                                "tools": ["filesystem.read_file"],
                            }
                        }
                    }
                }
            }
        }
        engine._workspace_root = tmp_path
        engine.active_agent_profile = profile
        engine._normalize_confirmation_policy = PocketCodeEngine._normalize_confirmation_policy.__get__(
            engine,
            PocketCodeEngine,
        )
        engine._refresh_runtime_components = lambda: None
        engine._runtime_config = {}
        engine._tool_confirmation_config = {}
        engine._maybe_refresh_runtime_components = lambda: None

        refreshed = engine.save_agent_profile_tools("coder.safe", ["filesystem.read_file"])

        assert refreshed is manager.saved_profile
        assert manager.saved_profile is not None
        assert manager.saved_profile.tools == ["filesystem.read_file"]
        textual = engine._config["runtime"]["textual"]
        assert textual["last_used"]["agent_profiles"]["coder.safe"]["tools"] == ["filesystem.read_file"]

    def test_list_tools_for_agent_caches_unfiltered_results(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._catalog = _CatalogWithToolResolution()
        engine.active_agent_profile = None
        engine.enabled_skills = []
        engine._skill_manager = _SkillManagerStub({})
        engine._agent_tools_cache = {}

        first = engine.list_tools_for_agent("coder.coder")
        second = engine.list_tools_for_agent("coder.coder")

        assert first == ["tool.a", "tool.b"]
        assert second == ["tool.a", "tool.b"]
        assert engine._catalog.resolve_call_count == 1

    def test_list_tools_for_agent_accepts_typed_flow_reference(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        registry = NamespaceRegistry()
        registry.register(
            "coder",
            "coder",
            type("Defn", (), {"metadata": {"namespace": "core"}, "default_agent_profile": None})(),
        )
        engine._catalog = type(
            "Plugins",
            (),
            {
                "agents": registry,
                "resolve_tools_for_agent": staticmethod(lambda agent_name: ["core.read_file"]),
            },
        )()
        engine.active_agent_profile = AgentProfile(
            name="coder.safe",
            flow="coder.coder",
            tools=["core.read_file"],
        )
        engine.enabled_skills = []
        engine._skill_manager = _SkillManagerStub({})
        engine._agent_tools_cache = {}

        result = engine.list_tools_for_agent("flow:coder.coder")

        assert result == ["core.read_file"]

    def test_set_agent_llm_override_accepts_typed_agent_reference(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        registry = NamespaceRegistry()
        registry.register("coder", "coder", object())
        engine._catalog = type("Plugins", (), {"agents": registry})()
        engine._llm_router = type(
            "Router",
            (),
            {"resolve_profile_config": staticmethod(lambda name: {"profile_name": name})},
        )()
        engine.agent_llm_overrides = {}

        engine.set_agent_llm_override("agent:coder.coder", "fast")

        assert engine.agent_llm_overrides == {"coder.coder": "fast"}

    def test_enable_skill_registers_provided_tools_and_resolves_existing_tool_refs(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._catalog = _CatalogWithQualifiedTools()
        engine._skill_manager = _SkillManagerStub(
            {
                "python-testing": SkillDefinition(
                    name="python-testing",
                    tool_refs=["read_file"],
                    provided_tools={"skill.python_testing.run_pytest": lambda **kw: {"ok": True}},
                )
            }
        )
        engine._runtime_config = {}
        engine._tool_confirmation_config = {"default_policy": None, "tool_policies": {}, "agent_policies": {}}
        engine._llm_router = object()
        engine.enabled_skills = []
        engine.current_agent = "coder.coder"
        engine.active_agent_profile = None

        engine.enable_skill("python-testing")

        assert engine.enabled_skills == ["python-testing"]
        assert engine._active_skill_existing_tool_refs() == ["core.read_file"]
        assert "skill.python_testing.run_pytest" in engine._tool_runtime.tools

    def test_save_system_settings_persists_workspace_config(self, tmp_path):
        config_path = tmp_path / "pocketcode.yml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "llm": {
                        "providers": {"gemini": {"api_key": "${GEMINI_API_KEY}"}},
                        "profiles": {"fast": {"provider": "gemini", "model": "gemini-2.5-flash"}},
                        "default_profile": "fast",
                    },
                    "runtime": {"default_agent": "coder.coder"},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        engine._config = {
            "llm": {
                "providers": {"gemini": {"api_key": "${GEMINI_API_KEY}"}},
                "profiles": {"fast": {"provider": "gemini", "model": "gemini-2.5-flash"}},
                "default_profile": "fast",
            },
            "runtime": {"default_agent": "coder.coder"},
        }
        engine._runtime_config = engine._config["runtime"]
        engine._llm_config = engine._config["llm"]
        engine._catalog = type("Plugins", (), {"agents": {"coder.coder": object(), "asker.asker": object()}})()
        engine._llm_router = type(
            "Router",
            (),
            {"resolve_profile_config": staticmethod(lambda name: {"profile_name": name}), "default_profile_name": "fast"},
        )()
        engine._reload_llm_runtime = lambda: None

        saved_path = engine.save_system_settings(
            theme_name="forest",
            workspace_view="review",
            default_agent="asker.asker",
            default_llm_profile="fast",
            control_presentation="modal",
        )

        saved = yaml.safe_load(saved_path.read_text(encoding="utf-8"))
        assert saved["runtime"]["default_agent"] == "asker.asker"
        assert saved["runtime"]["textual"] == {
            "theme_name": "forest",
            "workspace_view": "review",
            "control_presentation": "modal",
        }
        assert saved["llm"]["default_profile"] == "fast"

    def test_save_system_settings_persists_canonical_default_agent_for_registry(self, tmp_path):
        config_path = tmp_path / "pocketcode.yml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "llm": {
                        "providers": {"gemini": {"api_key": "${GEMINI_API_KEY}"}},
                        "profiles": {"fast": {"provider": "gemini", "model": "gemini-2.5-flash"}},
                        "default_profile": "fast",
                    },
                    "runtime": {"default_agent": "core.react"},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        engine._config = {
            "llm": {
                "providers": {"gemini": {"api_key": "${GEMINI_API_KEY}"}},
                "profiles": {"fast": {"provider": "gemini", "model": "gemini-2.5-flash"}},
                "default_profile": "fast",
            },
            "runtime": {"default_agent": "core.react"},
        }
        engine._runtime_config = engine._config["runtime"]
        engine._llm_config = engine._config["llm"]
        registry = NamespaceRegistry()
        registry.register("core", "react", object())
        engine._catalog = type("Plugins", (), {"agents": registry})()
        engine._llm_router = type(
            "Router",
            (),
            {"resolve_profile_config": staticmethod(lambda name: {"profile_name": name}), "default_profile_name": "fast"},
        )()
        engine._reload_llm_runtime = lambda: None

        saved_path = engine.save_system_settings(
            theme_name="forest",
            workspace_view="review",
            default_agent="core.react",
            default_llm_profile="fast",
            control_presentation="inline",
        )

        saved = yaml.safe_load(saved_path.read_text(encoding="utf-8"))
        assert saved["runtime"]["default_agent"] == "core.react"

    def test_get_system_settings_returns_control_presentation(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._runtime_config = {"textual": {"control_presentation": "modal"}}
        engine._llm_config = {"default_profile": "fast"}
        engine._catalog = type("Plugins", (), {"agents": {}})()

        settings = engine.get_system_settings()

        assert settings["control_presentation"] == "modal"

    def test_set_last_used_entry_history_persists_trimmed_history(self, tmp_path):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        engine._config = {"runtime": {"textual": {}}}
        engine._runtime_config = engine._config["runtime"]

        engine.set_last_used_entry_history([" first ", "", "second", "third"])

        history_file = tmp_path / ".pockethist" / "textual_entry_history.json"
        assert json.loads(history_file.read_text(encoding="utf-8")) == ["first", "second", "third"]
        assert engine.get_textual_entry_history() == ["first", "second", "third"]

    def test_set_last_used_entry_history_uses_configured_history_dir(self, tmp_path):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        engine._config = {"runtime": {"storage": {"entry_history_dir": ".custom-hist"}}}
        engine._runtime_config = engine._config["runtime"]

        engine.set_last_used_entry_history(["updated value"])

        assert json.loads((tmp_path / ".custom-hist" / "textual_entry_history.json").read_text(encoding="utf-8")) == [
            "updated value"
        ]

    def test_configured_enabled_skills_uses_default_skills_without_session_override(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._config = {
            "runtime": {
                "textual": {
                    "default_skills": ["python-lint"],
                    "last_used": {"skills": ["python-testing", "missing-skill"]},
                }
            }
        }
        engine._skill_manager = _SkillManagerStub(
            {
                "python-lint": SkillDefinition(name="python-lint"),
                "python-testing": SkillDefinition(name="python-testing"),
            }
        )

        assert engine._configured_enabled_skills() == ["python-lint"]

    def test_set_last_used_profile_tools_updates_session_override(self, tmp_path):
        profile = AgentProfile(name="coder.safe", flow="coder.coder", tools=["tool.read"])
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        engine._config = {"runtime": {"textual": {}}}
        engine._agent_profile_manager = _ProfileManagerStub({"coder.safe": profile})
        engine.active_agent_profile = profile

        engine.set_last_used_profile_tools("coder.safe", ["tool.write"])

        assert engine.active_agent_profile is not None
        assert engine.active_agent_profile.tools == ["tool.write"]
        assert engine.session_profile_overrides["coder.safe"]["tools"] == ["tool.write"]
        assert not (tmp_path / "pocketcode.yml").exists()

    def test_set_last_used_profile_skills_updates_session_override(self, tmp_path):
        profile = AgentProfile(name="coder.safe", flow="coder.coder", tools=["tool.read"])
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        engine._config = {"runtime": {"textual": {"default_skills": ["python-lint"]}}}
        engine._agent_profile_manager = _ProfileManagerStub({"coder.safe": profile})
        engine._skill_manager = _SkillManagerStub(
            {
                "python-lint": SkillDefinition(name="python-lint"),
                "python-testing": SkillDefinition(name="python-testing"),
            }
        )
        engine.active_agent_profile = profile
        engine.enabled_skills = ["python-lint"]
        engine._refresh_runtime_components = lambda: None

        engine.set_last_used_profile_skills("coder.safe", ["python-testing"])

        assert engine.enabled_skills == ["python-testing"]
        assert engine.session_profile_overrides["coder.safe"]["skills"] == ["python-testing"]
        assert not (tmp_path / "pocketcode.yml").exists()

    def test_reset_last_used_skills_restores_default_skill_config(self, tmp_path):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        engine._config = {
            "runtime": {
                "textual": {
                    "default_skills": ["python-lint"],
                    "last_used": {"skills": ["python-testing"]},
                }
            }
        }
        engine._skill_manager = _SkillManagerStub(
            {
                "python-lint": SkillDefinition(name="python-lint"),
                "python-testing": SkillDefinition(name="python-testing"),
            }
        )
        engine.enabled_skills = ["python-testing"]
        engine._refresh_runtime_components = lambda: None
        engine.session_global_skills_override = ["python-testing"]

        engine.reset_last_used_skills()

        assert engine.enabled_skills == ["python-lint"]
        assert engine.session_global_skills_override is None
        assert not (tmp_path / "pocketcode.yml").exists()

    def test_configured_enabled_skills_prefers_session_profile_skill_override(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._config = {
            "runtime": {
                "textual": {
                    "default_skills": ["python-lint"],
                    "last_used": {
                        "skills": ["python-testing"],
                        "agent_profiles": {
                            "coder.safe": {
                                "skills": ["azure-prepare", "missing-skill"],
                            }
                        },
                    },
                }
            }
        }
        engine.active_agent_profile = AgentProfile(name="coder.safe", flow="coder.coder")
        engine.session_profile_overrides = {"coder.safe": {"skills": ["azure-prepare", "missing-skill"]}}
        engine._skill_manager = _SkillManagerStub(
            {
                "python-lint": SkillDefinition(name="python-lint"),
                "python-testing": SkillDefinition(name="python-testing"),
                "azure-prepare": SkillDefinition(name="azure-prepare"),
            }
        )

        assert engine._configured_enabled_skills() == ["azure-prepare"]

    def test_configured_enabled_skills_uses_profile_yaml_before_global_defaults(self):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._config = {
            "runtime": {
                "textual": {
                    "default_skills": ["python-lint"],
                    "last_used": {
                        "skills": ["python-testing"],
                    },
                }
            }
        }
        engine.active_agent_profile = AgentProfile(
            name="coder.safe",
            flow="coder.coder",
            skills=["azure-prepare", "missing-skill"],
        )
        engine._agent_profile_manager = _ProfileManagerStub({"coder.safe": engine.active_agent_profile})
        engine._skill_manager = _SkillManagerStub(
            {
                "python-lint": SkillDefinition(name="python-lint"),
                "python-testing": SkillDefinition(name="python-testing"),
                "azure-prepare": SkillDefinition(name="azure-prepare"),
            }
        )

        assert engine._configured_enabled_skills() == ["azure-prepare"]

    def test_set_last_used_global_llm_profile_persists_textual_selection(self, tmp_path):
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        engine._config = {"runtime": {"textual": {}}}
        engine._runtime_config = engine._config["runtime"]
        engine._llm_router = type(
            "Router",
            (),
            {"resolve_profile_config": staticmethod(lambda name: {"profile_name": name})},
        )()
        engine.global_llm_override = None

        engine.set_last_used_global_llm_profile("smart")

        saved = yaml.safe_load((tmp_path / "pocketcode.yml").read_text(encoding="utf-8"))
        assert engine.global_llm_override == "smart"
        assert saved["runtime"]["textual"]["last_used"]["global_llm_profile"] == "smart"

    def test_save_and_apply_textual_selection_preset_round_trips_runtime_state(self, tmp_path):
        profile = AgentProfile(name="coder.safe", flow="coder.coder", source="workspace")
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        engine._config = {"runtime": {"textual": {}}}
        engine._runtime_config = engine._config["runtime"]
        engine._agent_profile_manager = _ProfileManagerStub({"coder.safe": profile})
        engine._catalog = type("Plugins", (), {"agents": {"coder.coder": object()}})()
        engine._skill_manager = _SkillManagerStub({"python-testing": SkillDefinition(name="python-testing")})
        engine._llm_router = type(
            "Router",
            (),
            {"resolve_profile_config": staticmethod(lambda name: {"profile_name": name})},
        )()
        engine._refresh_runtime_components = lambda: None
        engine.current_agent = "coder.coder"
        engine.active_agent_profile = profile
        engine.global_llm_override = "smart"
        engine.enabled_skills = ["python-testing"]
        engine.auto_confirm_tools = True
        engine.session_confirmation_overrides = {
            "default_policy": "confirm",
            "tool_policies": {},
            "agent_policies": {},
        }

        engine.save_textual_selection_preset("review-set")
        engine.active_agent_profile = None
        engine.global_llm_override = None
        engine.enabled_skills = []
        engine.auto_confirm_tools = False
        engine.clear_session_confirmation_overrides()

        engine.apply_textual_selection_preset("review-set")

        saved = yaml.safe_load((tmp_path / "pocketcode.yml").read_text(encoding="utf-8"))
        assert engine.active_agent_profile is not None
        assert engine.active_agent_profile.name == "coder.safe"
        assert engine.global_llm_override == "smart"
        assert engine.enabled_skills == ["python-testing"]
        assert engine.auto_confirm_tools is True
        assert engine.session_confirmation_overrides["default_policy"] == "confirm"
        assert "review-set" in saved["runtime"]["textual"]["selection_presets"]

    def test_save_textual_selection_preset_canonicalizes_profile_tool_refs(self, tmp_path):
        profile = AgentProfile(name="coder.safe", flow="coder.coder", source="workspace")
        engine = PocketCodeEngine.__new__(PocketCodeEngine)
        engine._workspace_root = tmp_path
        engine._config = {"runtime": {"textual": {}}}
        engine._runtime_config = engine._config["runtime"]
        engine._agent_profile_manager = _ProfileManagerStub({"coder.safe": profile})
        engine._catalog = type("Plugins", (), {"agents": {"coder.coder": object()}})()
        engine._skill_manager = _SkillManagerStub({"python-testing": SkillDefinition(name="python-testing")})
        engine._llm_router = type(
            "Router",
            (),
            {"resolve_profile_config": staticmethod(lambda name: {"profile_name": name})},
        )()
        engine._refresh_runtime_components = lambda: None
        engine.current_agent = "coder.coder"
        engine.active_agent_profile = profile
        engine.global_llm_override = "smart"
        engine.enabled_skills = ["python-testing"]
        engine.auto_confirm_tools = True
        engine.session_global_skills_override = None
        engine.session_confirmation_overrides = {
            "default_policy": "confirm",
            "tool_policies": {},
            "agent_policies": {},
        }
        engine.session_profile_overrides = {
            "coder.safe": {
                "tools": ["tool:filesystem.read_file", "search.web_search"],
                "tool_confirmation_overrides": {
                    "tool:filesystem.delete_file": "deny",
                },
            }
        }

        engine.save_textual_selection_preset("review-set")

        saved = yaml.safe_load((tmp_path / "pocketcode.yml").read_text(encoding="utf-8"))
        preset = saved["runtime"]["textual"]["selection_presets"]["review-set"]
        assert preset["agent_profiles"]["coder.safe"] == {
            "tools": ["filesystem.read_file", "search.web_search"],
            "tool_confirmation_overrides": {
                "filesystem.delete_file": "deny",
            },
            "skills": ["python-testing"],
        }
