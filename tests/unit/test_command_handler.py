from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pocketcode.cli.command_handler import handle_command, list_command_suggestions


class _EngineStub:
    def list_agents(self):
        return []

    def list_prompts(self):
        return []

    def list_modes(self):
        return []

    def list_skills(self):
        return []

    def list_llm_profiles(self):
        return []

    def list_agent_profiles(self, agent_name=None):
        return []

    def get_active_skills(self):
        return []


class _ViewCommandRecorder:
    def __init__(self):
        self.current_view = "chat"
        self.opened = 0
        self.set_calls: list[tuple[str, bool]] = []

    def open_picker(self):
        self.opened += 1

    def set_view(self, view_name, *, announce=False):
        self.current_view = view_name
        self.set_calls.append((view_name, announce))

    def get_view(self):
        return self.current_view


class _SessionCommandEngineStub(_EngineStub):
    def __init__(self):
        self._sessions = [
            {
                "session_id": "session-1",
                "title": "First session",
                "updated_at": "2026-03-07T10:00:00+00:00",
                "is_active": True,
                "is_resumable": True,
            },
            {
                "session_id": "session-2",
                "title": "Earlier work",
                "updated_at": "2026-03-07T09:00:00+00:00",
                "is_active": False,
                "is_resumable": True,
            },
        ]
        self.current_session = {
            "session_id": "session-1",
            "title": "First session",
            "updated_at": "2026-03-07T10:00:00+00:00",
            "loaded_from_history": False,
        }
        self.started = 0
        self.resumed: list[str] = []
        self.deleted: list[str] = []
        self.cleared = 0

    def get_active_session_info(self):
        return dict(self.current_session)

    def list_saved_sessions(self):
        return [dict(item) for item in self._sessions]

    def start_new_session(self):
        self.started += 1
        self.current_session = {
            "session_id": f"session-new-{self.started}",
            "title": f"Session {self.started}",
            "updated_at": "2026-03-07T11:00:00+00:00",
            "loaded_from_history": False,
        }
        return dict(self.current_session)

    def resume_session(self, session_id):
        self.resumed.append(session_id)
        self.current_session = {
            "session_id": session_id,
            "title": "Earlier work",
            "updated_at": "2026-03-07T09:00:00+00:00",
            "loaded_from_history": True,
        }
        return dict(self.current_session)

    def delete_session(self, session_id):
        if session_id == self.current_session["session_id"]:
            raise ValueError("Cannot delete the active session.")
        self.deleted.append(session_id)
        self._sessions = [item for item in self._sessions if item["session_id"] != session_id]
        return {"session_id": session_id, "deleted": True}

    def clear_saved_sessions(self):
        prior = [item for item in self._sessions if item["session_id"] != self.current_session["session_id"]]
        self.cleared += len(prior)
        self._sessions = [item for item in self._sessions if item["session_id"] == self.current_session["session_id"]]
        return len(prior)


class _PromptListingEngineStub(_EngineStub):
    def list_prompts(self):
        return ["core.react", "workspace.review"]


class _FlowSelectionEngineStub(_EngineStub):
    def __init__(self):
        self.set_flow_calls = []

    def set_flow(self, flow_name):
        self.set_flow_calls.append(flow_name)


class _DuplicateAgentListingEngineStub(_EngineStub):
    def list_available_agents(self):
        return ["coder.safe", "coder.safe", "review.safe"]

    def get_agent_profile(self, name=None):
        if name is None:
            return SimpleNamespace(name="coder.safe")
        return SimpleNamespace(name=name)


class _AgentListingEngineStub(_EngineStub):
    def list_available_agents(self):
        return ["core::react", "coder.safe", "review.safe"]

    def get_agent_profile(self, name=None):
        profiles = {
            "core::react": SimpleNamespace(name="core::react", source="synthesised"),
            "coder.safe": SimpleNamespace(name="coder.safe", source="workspace"),
            "review.safe": SimpleNamespace(name="review.safe", source="plugin"),
        }
        if name is None:
            return profiles["coder.safe"]
        return profiles.get(name)


class _RunHandleStub:
    def __init__(self, cancel_result=True):
        self.cancel_result = cancel_result
        self.reasons = []

    def cancel(self, reason):
        self.reasons.append(reason)
        return self.cancel_result


class _EditableProfileEngineStub(_EngineStub):
    def __init__(self):
        self.profile = SimpleNamespace(
            name="coder.safe",
            agent="coder::coder",
            source="workspace",
            source_path=Path("/tmp/coder.safe.yaml"),
            llm_profile="fast",
            extra_prompts=["prompts/base.md"],
            tools=["tool.read"],
            tool_confirmation={
                "default": "confirm",
                "overrides": {"tool.write": "deny"},
            },
        )
        self.updated_calls = []
        self.cloned_calls = []

    def get_agent_profile(self, name=None):
        if name == self.profile.name or name is None:
            return self.profile
        return None

    def list_tools_for_agent(self, agent_name):
        assert agent_name == self.profile.agent
        return ["tool.read", "tool.write", "tool.search"]

    def update_agent_profile(
        self,
        name,
        *,
        llm_profile,
        tools,
        extra_prompts,
        tool_confirmation_default,
        tool_confirmation_overrides,
    ):
        self.updated_calls.append(
            {
                "name": name,
                "llm_profile": llm_profile,
                "tools": tools,
                "extra_prompts": extra_prompts,
                "tool_confirmation_default": tool_confirmation_default,
                "tool_confirmation_overrides": tool_confirmation_overrides,
            }
        )

    def clone_agent_profile(self, src_name, new_name):
        self.cloned_calls.append((src_name, new_name))
        return SimpleNamespace(name=new_name, source_path=Path(f"/tmp/{new_name}.yaml"))


class _ModeSkillEngineStub(_EngineStub):
    def __init__(self):
        self.active_mode = None
        self.active_skills = []
        self.mode_switches = []
        self.skill_enabled = []
        self.skill_disabled = []

    def list_modes(self):
        return ["review", "build"]

    def list_skills(self):
        return ["python-testing", "azure-prepare"]

    def get_mode(self, name=None):
        modes = {
            "review": SimpleNamespace(
                name="review",
                description="Review mode",
                flow="core::react",
                agent=None,
                llm_profile="smart",
                tools=["core.read_file"],
                tools_specified=True,
                extra_prompts=["prompts/review.md"],
                tool_confirmation={"default": "confirm"},
                source_path=Path("/tmp/review.md"),
            ),
            "build": SimpleNamespace(
                name="build",
                description="Build mode",
                flow="core::react",
                agent=None,
                llm_profile=None,
                tools=None,
                tools_specified=False,
                extra_prompts=[],
                tool_confirmation={},
                source_path=Path("/tmp/build.md"),
            ),
        }
        if name is None:
            return self.active_mode
        return modes.get(name)

    def set_mode(self, name):
        self.mode_switches.append(name)
        self.active_mode = self.get_mode(name) if name is not None else None

    def get_skill(self, name):
        skills = {
            "python-testing": SimpleNamespace(
                name="python-testing",
                description="Pytest workflow",
                tool_refs=["core.read_file"],
                provided_tools={"skill.python_testing.run_pytest": object()},
                extra_prompts=["references/style.md"],
                references=["references/style.md"],
                scripts=["scripts/run_pytest.py"],
                assets=["assets/template.txt"],
                source_path=Path("/tmp/python-testing/SKILL.md"),
            )
        }
        return skills.get(name)

    def get_active_skills(self):
        return [SimpleNamespace(name=name) for name in self.active_skills]

    def enable_skill(self, name):
        self.skill_enabled.append(name)
        if name not in self.active_skills:
            self.active_skills.append(name)

    def disable_skill(self, name):
        self.skill_disabled.append(name)
        self.active_skills = [skill for skill in self.active_skills if skill != name]


class _StatusEngineStub(_EngineStub):
    def status(self):
        return {
            "runtime_flow": "internal-router",
            "flow": "core::react",
            "agent": "coder.safe",
            "mode": "review",
            "skills": ["python-testing"],
            "global_llm_override": None,
            "agent_llm_overrides": {},
            "handoff_llm_overrides": {},
            "config_llm_overrides": {},
            "default_llm_profile": "balanced",
            "tool_confirmation": {},
            "session_tool_confirmation_overrides": {},
            "last_run_summary": {},
        }


class _WarningStatusEngineStub(_EngineStub):
    def status(self):
        return {
            "runtime_flow": "internal-router",
            "flow": "core::react",
            "agent": "coder.safe",
            "mode": "review",
            "skills": ["python-testing"],
            "global_llm_override": None,
            "agent_llm_overrides": {},
            "handoff_llm_overrides": {},
            "config_llm_overrides": {},
            "default_llm_profile": "balanced",
            "tool_confirmation": {},
            "session_tool_confirmation_overrides": {},
            "last_run_summary": {
                "vm_validation_warnings": [
                    {
                        "code": "legacy-tool-loop",
                        "message": "Prefer tool-once.",
                        "location": "line 4, cols 1-12",
                        "span": {
                            "start_line": 4,
                            "start_column": 1,
                            "end_line": 4,
                            "end_column": 12,
                        },
                    },
                    {
                        "code": "legacy-prompt-route",
                        "message": "Prefer prompt-route.",
                        "location": "line 9, cols 5-22",
                        "span": {
                            "start_line": 9,
                            "start_column": 5,
                            "end_line": 9,
                            "end_column": 22,
                        },
                    },
                ]
            },
        }


class _AssetCommandEngineStub(_EngineStub):
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.created_calls: list[tuple[str, str]] = []
        self.list_calls: list[str] = []
        self.show_calls: list[tuple[str, str]] = []
        self.clone_calls: list[tuple[str, str, str]] = []
        self.edit_calls: list[tuple[str, str, str]] = []
        self.delete_calls: list[tuple[str, str]] = []

    def create_markdown_asset(self, asset_kind: str, name: str):
        self.created_calls.append((asset_kind, name))
        target_dir = self.workspace_root / ".pocketcode" / f"{asset_kind}s"
        target_dir.mkdir(parents=True, exist_ok=True)
        asset_path = target_dir / f"{name}.md"
        asset_path.write_text(f"{asset_kind}:{name}\n", encoding="utf-8")
        companion_path = None
        if asset_kind == "tool":
            companion_path = target_dir / f"{name}.py"
            companion_path.write_text("class Placeholder: pass\n", encoding="utf-8")
        return {
            "kind": asset_kind,
            "name": name,
            "path": asset_path,
            "companion_path": companion_path,
        }

    def list_markdown_assets(self, asset_kind: str):
        self.list_calls.append(asset_kind)
        return [f"{asset_kind}.one", f"{asset_kind}.two"]

    def get_markdown_asset(self, asset_kind: str, name: str):
        self.show_calls.append((asset_kind, name))
        asset_path = self.workspace_root / ".pocketcode" / f"{asset_kind}s" / f"{name}.md"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text(f"---\nname: {name}\n---\nbody\n", encoding="utf-8")
        return {
            "kind": asset_kind,
            "name": name,
            "path": asset_path,
            "companion_path": None,
            "text": asset_path.read_text(encoding="utf-8"),
        }

    def clone_markdown_asset(self, asset_kind: str, source_name: str, new_name: str):
        self.clone_calls.append((asset_kind, source_name, new_name))
        target_dir = self.workspace_root / ".pocketcode" / f"{asset_kind}s"
        target_dir.mkdir(parents=True, exist_ok=True)
        asset_path = target_dir / f"{new_name}.md"
        asset_path.write_text(f"clone:{source_name}->{new_name}\n", encoding="utf-8")
        companion_path = None
        if asset_kind == "tool":
            companion_path = target_dir / f"{new_name}.py"
            companion_path.write_text("class Placeholder: pass\n", encoding="utf-8")
        return {
            "kind": asset_kind,
            "name": new_name,
            "path": asset_path,
            "companion_path": companion_path,
        }

    def update_markdown_asset(self, asset_kind: str, name: str, *, markdown_text: str):
        self.edit_calls.append((asset_kind, name, markdown_text))
        asset_path = self.workspace_root / ".pocketcode" / f"{asset_kind}s" / f"{name}.md"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text(markdown_text, encoding="utf-8")
        return {
            "kind": asset_kind,
            "name": name,
            "path": asset_path,
            "companion_path": None,
        }

    def delete_markdown_asset(self, asset_kind: str, name: str):
        self.delete_calls.append((asset_kind, name))
        asset_path = self.workspace_root / ".pocketcode" / f"{asset_kind}s" / f"{name}.md"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text("to-delete\n", encoding="utf-8")
        companion_path = None
        if asset_kind == "tool":
            companion_path = asset_path.with_suffix(".py")
            companion_path.write_text("class Placeholder: pass\n", encoding="utf-8")
        asset_path.unlink()
        return {
            "kind": asset_kind,
            "name": name,
            "path": asset_path,
            "companion_path": companion_path,
            "companion_deleted": False,
        }


class _FailingAssetEditEngineStub(_AssetCommandEngineStub):
    def update_markdown_asset(self, asset_kind: str, name: str, *, markdown_text: str):
        raise ValueError("Tool handler file not found: /tmp/missing_tool.py")


class TestCommandHandlerParsing:
    def test_universal_command_suggestions_exclude_textual_only_commands(self):
        suggestions = list_command_suggestions(_EngineStub())

        assert "/help" in suggestions
        assert "/agent" in suggestions
        assert "/asset" in suggestions
        assert "/copy" not in suggestions
        assert "/copy-all" not in suggestions
        assert "/view" not in suggestions

    def test_textual_command_suggestions_include_view_commands(self):
        suggestions = list_command_suggestions(_EngineStub(), interface_name="textual")

        assert "/view" in suggestions
        assert "/view switch run" in suggestions

    def test_universal_help_excludes_textual_only_commands(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
            "interface": "one-shot",
        }

        handle_command(
            "/help",
            engine=_EngineStub(),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "/copy" not in captured.out
        assert "Textual UI shortcuts" not in captured.out

    def test_textual_help_includes_textual_only_commands(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
            "interface": "textual",
        }

        handle_command(
            "/help",
            engine=_EngineStub(),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "Textual-only commands:" in captured.out
        assert "/copy" in captured.out
        assert "/copy-all" in captured.out
        assert "/view" in captured.out

    def test_asset_help_lists_create_commands(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }

        handle_command("/asset help", engine=_EngineStub(), cli_context=cli_context)

        captured = capsys.readouterr()
        assert "/asset create agent <name>" in captured.out
        assert "/asset create flow <name>" in captured.out
        assert "/asset create tool <name>" in captured.out
        assert "/asset clone <kind> <source> <new_name>" in captured.out
        assert "/asset edit <kind> <name> <file>" in captured.out
        assert "/asset delete <kind> <name> --yes" in captured.out

    def test_asset_list_prints_workspace_markdown_assets(self, tmp_path, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }
        engine = _AssetCommandEngineStub(tmp_path)

        handle_command("/asset list flow", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert engine.list_calls == ["flow"]
        assert "Workspace markdown flow assets:" in captured.out
        assert "flow.one" in captured.out
        assert "flow.two" in captured.out

    def test_asset_show_prints_path_and_markdown_source(self, tmp_path, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }
        engine = _AssetCommandEngineStub(tmp_path)

        handle_command("/asset show tool sample_tool", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert engine.show_calls == [("tool", "sample_tool")]
        assert "Asset: tool sample_tool" in captured.out
        assert ".pocketcode/tools/sample_tool.md" in captured.out
        assert "name: sample_tool" in captured.out

    def test_asset_create_tool_creates_markdown_and_handler(self, tmp_path, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }
        engine = _AssetCommandEngineStub(tmp_path)

        handle_command("/asset create tool sample_tool", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        asset_path = tmp_path / ".pocketcode" / "tools" / "sample_tool.md"
        handler_path = tmp_path / ".pocketcode" / "tools" / "sample_tool.py"
        assert engine.created_calls == [("tool", "sample_tool")]
        assert asset_path.is_file()
        assert handler_path.is_file()
        assert "Created tool markdown asset 'sample_tool'" in captured.out
        assert "Created companion handler" in captured.out
        assert "Reloaded runtime registries." in captured.out

    def test_asset_clone_tool_creates_markdown_and_handler_copy(self, tmp_path, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }
        engine = _AssetCommandEngineStub(tmp_path)

        handle_command(
            "/asset clone tool sample_tool sample_tool_copy",
            engine=engine,
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert engine.clone_calls == [("tool", "sample_tool", "sample_tool_copy")]
        assert "Cloned tool markdown asset 'sample_tool' -> 'sample_tool_copy'" in captured.out
        assert "Cloned companion handler" in captured.out
        assert "Reloaded runtime registries." in captured.out

    def test_asset_edit_updates_markdown_from_file(self, tmp_path, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }
        engine = _AssetCommandEngineStub(tmp_path)
        source_file = tmp_path / "edited-flow.md"
        source_file.write_text("---\nname: sample_flow\n---\nupdated\n", encoding="utf-8")

        handle_command(
            f"/asset edit flow sample_flow {source_file}",
            engine=engine,
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert engine.edit_calls == [("flow", "sample_flow", "---\nname: sample_flow\n---\nupdated\n")]
        assert "Updated flow markdown asset 'sample_flow'" in captured.out
        assert "Reloaded runtime registries." in captured.out

    def test_asset_edit_reports_tool_handler_validation_errors(self, tmp_path, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }
        engine = _FailingAssetEditEngineStub(tmp_path)
        source_file = tmp_path / "bad-tool.md"
        source_file.write_text("---\nname: bad-tool\n---\nbody\n", encoding="utf-8")

        handle_command(
            f"/asset edit tool bad-tool {source_file}",
            engine=engine,
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "Tool handler file not found" in captured.out

    def test_asset_delete_requires_yes(self, tmp_path, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }
        engine = _AssetCommandEngineStub(tmp_path)

        handle_command("/asset delete tool sample_tool", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert engine.delete_calls == []
        assert "Usage: /asset delete <agent|flow|tool> <name> --yes" in captured.out

    def test_asset_delete_tool_removes_markdown_and_leaves_handler(self, tmp_path, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }
        engine = _AssetCommandEngineStub(tmp_path)

        handle_command(
            "/asset delete tool sample_tool --yes",
            engine=engine,
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert engine.delete_calls == [("tool", "sample_tool")]
        assert "Deleted tool markdown asset 'sample_tool'" in captured.out
        assert "Left companion handler in place" in captured.out
        assert "Reloaded runtime registries." in captured.out

    def test_textual_only_command_reports_interface_scope_outside_textual(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
            "interface": "basic",
        }

        handle_command(
            "/copy",
            engine=_EngineStub(),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "available only in the Textual UI" in captured.out

    def test_view_command_opens_textual_picker(self, capsys):
        recorder = _ViewCommandRecorder()
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
            "interface": "textual",
            "textual_open_view_picker": recorder.open_picker,
            "textual_set_view": recorder.set_view,
            "textual_get_current_view": recorder.get_view,
        }

        handle_command("/view", engine=_EngineStub(), cli_context=cli_context)

        captured = capsys.readouterr()
        assert recorder.opened == 1
        assert "Opened the view selector." in captured.out

    def test_view_switch_command_updates_textual_view(self, capsys):
        recorder = _ViewCommandRecorder()
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
            "interface": "textual",
            "textual_open_view_picker": recorder.open_picker,
            "textual_set_view": recorder.set_view,
            "textual_get_current_view": recorder.get_view,
        }

        handle_command("/view switch run", engine=_EngineStub(), cli_context=cli_context)

        captured = capsys.readouterr()
        assert recorder.set_calls == [("run", True)]
        assert "View selected: run" in captured.out

    def test_status_output_uses_internal_flow_label(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }

        handle_command(
            "/status",
            engine=_StatusEngineStub(),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "Internal flow: internal-router" in captured.out
        assert "Selected flow: core::react" in captured.out
        assert "workflow" not in captured.out.lower()

    def test_status_output_includes_vm_validation_warning_codes_when_present(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }

        handle_command(
            "/status",
            engine=_WarningStatusEngineStub(),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "VM Validation Warnings: legacy-tool-loop, legacy-prompt-route" in captured.out

    def test_status_verbose_output_includes_vm_validation_warning_messages(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }

        handle_command(
            "/status verbose",
            engine=_WarningStatusEngineStub(),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "VM Validation Warnings: legacy-tool-loop, legacy-prompt-route" in captured.out
        assert "- legacy-tool-loop (line 4, cols 1-12): Prefer tool-once." in captured.out
        assert "- legacy-prompt-route (line 9, cols 5-22): Prefer prompt-route." in captured.out

    def test_context_add_snippet_uses_shell_style_quoting(self):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }

        handle_command(
            '/context add snippet note "line one with spaces"',
            engine=_EngineStub(),
            cli_context=cli_context,
        )

        assert cli_context["snippets"] == {"note": "line one with spaces"}

    def test_session_list_prints_title_and_timestamp(self, capsys):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command("/session list", engine=_SessionCommandEngineStub(), cli_context=cli_context)

        captured = capsys.readouterr()
        assert "First session" in captured.out
        assert "2026-03-07T10:00:00+00:00" in captured.out
        assert "Earlier work" in captured.out

    def test_session_show_reports_active_session(self, capsys):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command("/session show", engine=_SessionCommandEngineStub(), cli_context=cli_context)

        captured = capsys.readouterr()
        assert "Active session" in captured.out
        assert "session-1" in captured.out
        assert "First session" in captured.out

    def test_session_new_reports_created_session(self, capsys):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
        engine = _SessionCommandEngineStub()

        handle_command("/session new", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert engine.started == 1
        assert "Started new session" in captured.out
        assert "session-new-1" in captured.out

    def test_session_resume_reports_selected_session(self, capsys):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
        engine = _SessionCommandEngineStub()

        handle_command("/session resume session-2", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert engine.resumed == ["session-2"]
        assert "Resumed session" in captured.out
        assert "session-2" in captured.out

    def test_session_delete_requires_explicit_confirmation(self, capsys):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
        engine = _SessionCommandEngineStub()

        handle_command("/session delete session-2", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert engine.deleted == []
        assert "requires --yes" in captured.out

    def test_session_delete_blocks_active_session(self, capsys):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
        engine = _SessionCommandEngineStub()

        handle_command("/session delete session-1 --yes", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert engine.deleted == []
        assert "Cannot delete the active session" in captured.out

    def test_session_clear_all_requires_confirmation_and_preserves_active_session(self, capsys):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
        engine = _SessionCommandEngineStub()

        handle_command("/session clear-all", engine=engine, cli_context=cli_context)
        first = capsys.readouterr()
        assert engine.cleared == 0
        assert "requires --yes" in first.out

        handle_command("/session clear-all --yes", engine=engine, cli_context=cli_context)
        second = capsys.readouterr()
        assert engine.cleared == 1
        assert "Cleared 1 saved session" in second.out

    def test_invalid_quoted_command_returns_parse_error(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }

        handle_command(
            '/context add snippet note "unterminated',
            engine=_EngineStub(),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "Command parse error" in captured.out

    def test_stop_requests_cancellation_for_active_run(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }
        run_handle = _RunHandleStub()

        handle_command(
            "/stop",
            engine=_EngineStub(),
            cli_context=cli_context,
            active_run=run_handle,
        )

        assert run_handle.reasons == ["Run cancelled from CLI."]
        captured = capsys.readouterr()
        assert "Stop requested for the active run." in captured.out

    def test_stop_reports_missing_active_run(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }

        handle_command(
            "/stop",
            engine=_EngineStub(),
            cli_context=cli_context,
            active_run=None,
        )

        captured = capsys.readouterr()
        assert "No run is currently active." in captured.out

    def test_prompts_command_lists_registered_prompts(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }

        handle_command(
            "/prompts",
            engine=_PromptListingEngineStub(),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "Available prompts:" in captured.out
        assert "core.react" in captured.out
        assert "workspace.review" in captured.out

    def test_agent_command_no_longer_falls_back_to_flow_selection(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }
        engine = _FlowSelectionEngineStub()

        handle_command(
            "/agent coder::coder",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.set_flow_calls == []
        captured = capsys.readouterr()
        assert "Unknown /agent subcommand: coder::coder" in captured.out

    def test_flow_shortcut_alias_is_removed(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }

        handle_command(
            "/fl core::react",
            engine=_EngineStub(),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "Unknown command: /fl" in captured.out


class TestAgentEditingCommands:
    def test_agent_list_hides_synthesised_flow_defaults(self, capsys):
        engine = _AgentListingEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent list",
            engine=engine,
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "core::react" not in captured.out
        assert "coder.safe" in captured.out
        assert "review.safe" in captured.out

    def test_agent_list_deduplicates_profile_names(self, capsys):
        engine = _DuplicateAgentListingEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent list",
            engine=engine,
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert captured.out.count("coder.safe") == 1
        assert captured.out.count("review.safe") == 1

    def test_agent_clone_reports_workspace_path(self, capsys):
        engine = _EditableProfileEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent clone coder.safe coder.clone",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.cloned_calls == [("coder.safe", "coder.clone")]
        captured = capsys.readouterr()
        assert "/tmp/coder.clone.yaml" in captured.out

    def test_agent_tools_set_updates_allowed_tools(self, capsys):
        engine = _EditableProfileEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent tools coder.safe set tool.read tool.search",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.updated_calls == [
            {
                "name": "coder.safe",
                "llm_profile": "fast",
                "tools": ["tool.read", "tool.search"],
                "extra_prompts": ["prompts/base.md"],
                "tool_confirmation_default": "confirm",
                "tool_confirmation_overrides": {"tool.write": "deny"},
            }
        ]


class TestModeAndSkillCommands:
    def test_skill_list_groups_skills_by_prefix(self, capsys):
        engine = _ModeSkillEngineStub()
        engine.active_skills = ["python-testing"]
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command("/skill list", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert "Available skills:" in captured.out
        assert "  azure:" in captured.out
        assert "  python:" in captured.out
        assert "    * python-testing" in captured.out
        assert "      azure-prepare" in captured.out

    def test_list_skills_uses_the_same_grouped_output(self, capsys):
        engine = _ModeSkillEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command("/list skills", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert "  azure:" in captured.out
        assert "  python:" in captured.out

    def test_mode_switch_activates_mode(self, capsys):
        engine = _ModeSkillEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command("/mode switch review", engine=engine, cli_context=cli_context)

        assert engine.mode_switches == ["review"]
        captured = capsys.readouterr()
        assert "Mode activated: review" in captured.out

    def test_mode_show_prints_mode_details(self, capsys):
        engine = _ModeSkillEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command("/mode show review", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert "Mode: review" in captured.out
        assert "Flow     : core::react" in captured.out

    def test_skill_enable_updates_session(self, capsys):
        engine = _ModeSkillEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command("/skill enable python-testing", engine=engine, cli_context=cli_context)

        assert engine.skill_enabled == ["python-testing"]
        captured = capsys.readouterr()
        assert "Skill enabled: python-testing" in captured.out

    def test_skill_show_prints_provided_tools(self, capsys):
        engine = _ModeSkillEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command("/skill show python-testing", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert "Skill: python-testing" in captured.out
        assert "skill.python_testing.run_pytest" in captured.out

    def test_agent_tools_all_clears_allowlist(self, capsys):
        engine = _EditableProfileEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent tools coder.safe all",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.updated_calls[0]["tools"] is None
        captured = capsys.readouterr()
        assert "now allows all tools" in captured.out

    def test_agent_policy_default_updates_profile_default(self, capsys):
        engine = _EditableProfileEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent policy default coder.safe allow",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.updated_calls == [
            {
                "name": "coder.safe",
                "llm_profile": "fast",
                "tools": ["tool.read"],
                "extra_prompts": ["prompts/base.md"],
                "tool_confirmation_default": "allow",
                "tool_confirmation_overrides": {"tool.write": "deny"},
            }
        ]
        captured = capsys.readouterr()
        assert "default tool policy set to: allow" in captured.out

    def test_agent_policy_tool_updates_per_tool_override(self, capsys):
        engine = _EditableProfileEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent policy tool coder.safe tool.search confirm",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.updated_calls == [
            {
                "name": "coder.safe",
                "llm_profile": "fast",
                "tools": ["tool.read"],
                "extra_prompts": ["prompts/base.md"],
                "tool_confirmation_default": "confirm",
                "tool_confirmation_overrides": {
                    "tool.write": "deny",
                    "tool.search": "confirm",
                },
            }
        ]
        captured = capsys.readouterr()
        assert "tool.search -> confirm" in captured.out

    def test_agent_policy_tool_reset_removes_override(self, capsys):
        engine = _EditableProfileEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent policy tool coder.safe tool.write reset",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.updated_calls == [
            {
                "name": "coder.safe",
                "llm_profile": "fast",
                "tools": ["tool.read"],
                "extra_prompts": ["prompts/base.md"],
                "tool_confirmation_default": "confirm",
                "tool_confirmation_overrides": {},
            }
        ]
        captured = capsys.readouterr()
        assert "tool.write -> inherit" in captured.out

    def test_agent_tools_rejects_unknown_tool_name(self, capsys):
        engine = _EditableProfileEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent tools coder.safe set tool.read tool.ghost",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.updated_calls == []
        captured = capsys.readouterr()
        assert "unknown tool(s)" in captured.out

    def test_agent_edit_llm_updates_profile_llm(self, capsys):
        engine = _EditableProfileEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent edit llm coder.safe smart",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.updated_calls == [
            {
                "name": "coder.safe",
                "llm_profile": "smart",
                "tools": ["tool.read"],
                "extra_prompts": ["prompts/base.md"],
                "tool_confirmation_default": "confirm",
                "tool_confirmation_overrides": {"tool.write": "deny"},
            }
        ]
        captured = capsys.readouterr()
        assert "LLM updated: smart" in captured.out

    def test_agent_edit_prompts_replaces_prompt_paths(self, capsys):
        engine = _EditableProfileEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent edit prompts coder.safe prompts/review.md prompts/safety.md",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.updated_calls == [
            {
                "name": "coder.safe",
                "llm_profile": "fast",
                "tools": ["tool.read"],
                "extra_prompts": ["prompts/review.md", "prompts/safety.md"],
                "tool_confirmation_default": "confirm",
                "tool_confirmation_overrides": {"tool.write": "deny"},
            }
        ]
        captured = capsys.readouterr()
        assert "prompt paths updated" in captured.out


class TestWorkspaceCanonicalToolImports:
    def test_tools_package_exports_workspace_owned_git_class(self):
        from pocketcode.tools import GitStatusTool
        from pocketcode.core.workspace_module_loader import load_workspace_plugin_module

        workspace_git = load_workspace_plugin_module(".pocketcode", "plugins", "workspace_git", "tools", "git.py")

        assert GitStatusTool is workspace_git.GitStatusTool

    def test_legacy_context_shim_resolves_workspace_owned_class(self):
        from pocketcode.tools.context_elephant_store_tools import ReadContextElephantStoreFileTool
        from pocketcode.plugins.core.tools.context_elephant_store_tools import ReadContextElephantStoreFileTool as CoreTool
        from pocketcode.core.workspace_module_loader import load_workspace_plugin_module

        workspace_context = load_workspace_plugin_module(
            ".pocketcode", "plugins", "workspace_context", "tools", "context_elephant_store_tools.py"
        )

        assert ReadContextElephantStoreFileTool is CoreTool
        assert CoreTool is workspace_context.ReadContextElephantStoreFileTool
