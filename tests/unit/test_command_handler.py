from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pocketcode.cli.command_handler import handle_command, list_command_suggestions
from pocketcode.core.command_runtime import CommandResult, CommandSpec


class _EngineStub:
    def list_agents(self):
        return []

    def list_prompts(self):
        return []

    def list_skills(self):
        return []

    def list_llm_profiles(self):
        return []

    def list_agent_profiles(self, agent_name=None):
        return []

    def get_active_skills(self):
        return []

    def get_command_providers(self):
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


class _ProviderStub:
    def __init__(self, *commands, result=None):
        self._commands = list(commands)
        self.calls: list[tuple[str, list[str], object]] = []
        self.result = result or CommandResult(handled=True, output="provider handled")

    def list_commands(self, *, visibility="exported"):
        return [command for command in self._commands if getattr(command, "visibility", "exported") == visibility]

    def invoke(self, name, args, ctx):
        self.calls.append((name, list(args), ctx))
        return self.result


class _ProviderCommandEngineStub(_EngineStub):
    def __init__(self, provider=None, permission_error=None):
        self.provider = provider
        self.permission_error = permission_error

    def get_command_providers(self):
        return [self.provider] if self.provider is not None else []

    def invoke_registered_command(self, command_name, args, *, cli_context=None, caller_agent=None, capabilities=None):
        if self.permission_error is not None:
            raise self.permission_error
        normalized = str(command_name).lstrip("/")
        if self.provider is None:
            return None
        for spec in self.provider.list_commands(visibility="exported"):
            if spec.name == normalized:
                ctx = SimpleNamespace(
                    cli_context=dict(cli_context or {}),
                    caller_agent=caller_agent,
                    capabilities=set(capabilities or ()),
                )
                return self.provider.invoke(normalized, args, ctx)
        return None


class _SessionCommandEngineStub(_EngineStub):
    def __init__(self):
        self._sessions = [
            {
                "session_id": "session-1",
                "title": "First session",
                "updated_at": "2026-03-07T10:00:00+00:00",
                "is_active": True,
                "is_resumable": True,
                "debugger_breakpoint_count": 1,
                "debugger_breakpoints": ["until node review"],
            },
            {
                "session_id": "session-2",
                "title": "Earlier work",
                "updated_at": "2026-03-07T09:00:00+00:00",
                "is_active": False,
                "is_resumable": True,
                "debugger_breakpoint_count": 2,
                "debugger_breakpoints": [
                    "until tool core.write_file",
                    "until when pending_tool.name == \"core.write_file\"",
                ],
            },
        ]
        self.current_session = {
            "session_id": "session-1",
            "title": "First session",
            "updated_at": "2026-03-07T10:00:00+00:00",
            "loaded_from_history": False,
            "debugger_breakpoint_count": 1,
            "debugger_breakpoints": ["until node review"],
        }
        self.started = 0
        self.resumed: list[str] = []
        self.deleted: list[str] = []
        self.cleared = 0
        self.cleared_breakpoints: list[str] = []

    def get_active_session_info(self):
        return dict(self.current_session)

    def list_saved_sessions(self):
        return [dict(item) for item in self._sessions]

    def get_saved_session_details(self, session_id=None):
        target_id = session_id or self.current_session["session_id"]
        if target_id == self.current_session["session_id"]:
            return dict(self.current_session)
        for item in self._sessions:
            if item["session_id"] == target_id:
                return dict(item)
        return {}

    def start_new_session(self):
        self.started += 1
        self.current_session = {
            "session_id": f"session-new-{self.started}",
            "title": f"Session {self.started}",
            "updated_at": "2026-03-07T11:00:00+00:00",
            "loaded_from_history": False,
            "debugger_breakpoint_count": 0,
            "debugger_breakpoints": [],
        }
        return dict(self.current_session)

    def resume_session(self, session_id):
        self.resumed.append(session_id)
        self.current_session = {
            "session_id": session_id,
            "title": "Earlier work",
            "updated_at": "2026-03-07T09:00:00+00:00",
            "loaded_from_history": True,
            "debugger_breakpoint_count": 2,
            "debugger_breakpoints": [
                "until tool core.write_file",
                "until when pending_tool.name == \"core.write_file\"",
            ],
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

    def clear_saved_session_debugger_breakpoints(self, session_id):
        details = self.get_saved_session_details(session_id)
        labels = list(details.get("debugger_breakpoints", []))
        cleared = len(labels)
        self.cleared_breakpoints.append(session_id)
        for item in self._sessions:
            if item["session_id"] == session_id:
                item["debugger_breakpoint_count"] = 0
                item["debugger_breakpoints"] = []
        if self.current_session["session_id"] == session_id:
            self.current_session["debugger_breakpoint_count"] = 0
            self.current_session["debugger_breakpoints"] = []
        return {"session_id": session_id, "cleared": cleared}


class _PromptListingEngineStub(_EngineStub):
    def list_prompts(self):
        return ["core.react", "resource_root.pocketcode.review"]


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
        return ["core.react", "coder.safe", "review.safe"]

    def get_agent_profile(self, name=None):
        profiles = {
            "core.react": SimpleNamespace(name="core.react", source="synthesised"),
            "coder.safe": SimpleNamespace(name="coder.safe", source="workspace"),
            "review.safe": SimpleNamespace(name="review.safe", source="namespace"),
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


class _DebugRunnerRecorder:
    def __init__(self, result="debugged response"):
        self.calls: list[str] = []
        self.result = result

    def __call__(self, request: str):
        self.calls.append(request)
        return self.result


class _EditableProfileEngineStub(_EngineStub):
    def __init__(self):
        self.profile = SimpleNamespace(
            name="coder.safe",
            agent="coder.coder",
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
        self.active_skills = []
        self.skill_enabled = []
        self.skill_disabled = []

    def list_skills(self):
        return ["python-testing", "azure-prepare"]

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
            "flow": "core.react",
            "agent": "coder.safe",
            "skills": ["python-testing"],
            "global_llm_override": None,
            "agent_llm_overrides": {},
            "handoff_llm_overrides": {},
            "config_llm_overrides": {},
            "default_llm_profile": "balanced",
            "tool_confirmation": {},
            "session_tool_confirmation_overrides": {},
            "last_run_summary": {
                "runtime_event_count": 0,
                "step_count": 0,
                "runtime_effect_count": 0,
                "last_runtime_effect": {},
                "steps": [],
            },
        }


class _WarningStatusEngineStub(_EngineStub):
    def status(self):
        return {
            "runtime_flow": "internal-router",
            "flow": "core.react",
            "agent": "coder.safe",
            "skills": ["python-testing"],
            "global_llm_override": None,
            "agent_llm_overrides": {},
            "handoff_llm_overrides": {},
            "config_llm_overrides": {},
            "default_llm_profile": "balanced",
            "tool_confirmation": {},
            "session_tool_confirmation_overrides": {},
            "last_run_summary": {
                "runtime_event_count": 4,
                "step_count": 2,
                "runtime_effect_count": 2,
                "last_runtime_effect": {"kind": "call_tool", "payload": {"tool_name": "core.read_file"}},
                "steps": [
                    {
                        "index": 1,
                        "kind": "agent_turn",
                        "status": "completed",
                        "duration_ms": 12.0,
                        "summary": "Transition: call_tool",
                        "details": {"agent": "core.react"},
                    },
                    {
                        "index": 2,
                        "kind": "tool_call",
                        "status": "completed",
                        "duration_ms": 3.5,
                        "summary": "Succeeded: 'ok'",
                        "details": {"tool": "core.read_file"},
                    },
                ],
                "vm_validation_warnings": [
                    {
                        "code": "manual-tool-loop",
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
                        "code": "manual-prompt-route",
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

    def _asset_path(self, asset_kind: str, name: str) -> Path:
        root = self.workspace_root / ".pocketcode"
        if asset_kind == "agent":
            parts = [part for part in name.split(".") if part]
            group = parts[0]
            relative_parts = parts[1:] or [group]
            target_dir = root / f"agent.{group}"
            if len(relative_parts) > 1:
                target_dir = target_dir.joinpath(*relative_parts[:-1])
            return target_dir / f"{relative_parts[-1]}.agent.md"
        if asset_kind == "tool":
            return root / f"{name}.tool.md"
        return root / f"{name}.md"

    def _companion_path(self, asset_kind: str, name: str) -> Path | None:
        if asset_kind != "tool":
            return None
        return self.workspace_root / ".pocketcode" / f"{name}.tool.py"

    def create_markdown_asset(self, asset_kind: str, name: str):
        self.created_calls.append((asset_kind, name))
        asset_path = self._asset_path(asset_kind, name)
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text(f"{asset_kind}:{name}\n", encoding="utf-8")
        companion_path = self._companion_path(asset_kind, name)
        if companion_path is not None:
            companion_path.parent.mkdir(parents=True, exist_ok=True)
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
        asset_path = self._asset_path(asset_kind, name)
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text(f"---\nname: {name}\n---\nbody\n", encoding="utf-8")
        return {
            "kind": asset_kind,
            "name": name,
            "path": asset_path,
            "companion_path": self._companion_path(asset_kind, name),
            "text": asset_path.read_text(encoding="utf-8"),
        }

    def clone_markdown_asset(self, asset_kind: str, source_name: str, new_name: str):
        self.clone_calls.append((asset_kind, source_name, new_name))
        asset_path = self._asset_path(asset_kind, new_name)
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text(f"clone:{source_name}->{new_name}\n", encoding="utf-8")
        companion_path = self._companion_path(asset_kind, new_name)
        if companion_path is not None:
            companion_path.parent.mkdir(parents=True, exist_ok=True)
            companion_path.write_text("class Placeholder: pass\n", encoding="utf-8")
        return {
            "kind": asset_kind,
            "name": new_name,
            "path": asset_path,
            "companion_path": companion_path,
        }

    def update_markdown_asset(self, asset_kind: str, name: str, *, markdown_text: str):
        self.edit_calls.append((asset_kind, name, markdown_text))
        asset_path = self._asset_path(asset_kind, name)
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text(markdown_text, encoding="utf-8")
        return {
            "kind": asset_kind,
            "name": name,
            "path": asset_path,
            "companion_path": self._companion_path(asset_kind, name),
        }

    def delete_markdown_asset(self, asset_kind: str, name: str):
        self.delete_calls.append((asset_kind, name))
        asset_path = self._asset_path(asset_kind, name)
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text("to-delete\n", encoding="utf-8")
        companion_path = self._companion_path(asset_kind, name)
        if companion_path is not None:
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


class _StackVmCommandEngineStub(_EngineStub):
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.create_flow_calls: list[tuple[str, str, str | None]] = []
        self.create_script_calls: list[tuple[str, str]] = []
        self.create_agent_calls: list[tuple[str, str]] = []
        self.inspect_calls: list[tuple[str, str, str | None]] = []
        self.run_calls: list[dict[str, object]] = []
        self.update_script_calls: list[tuple[str, str]] = []
        self.update_markdown_calls: list[tuple[str, str, str]] = []

    def list_flows(self):
        return ["core.react", "resource_root.pocketcode.vm_review", "resource_root.pocketcode.vm_router"]

    def describe_flow(self, flow_name=None):
        vm_modes = {
            "resource_root.pocketcode.vm_review": "vm",
            "resource_root.pocketcode.vm_router": "vm",
            "core.react": "llm",
        }
        return {"name": flow_name, "execution_mode": vm_modes.get(flow_name, "llm")}

    def list_stackvm_scripts(self):
        return ["router.vm", "nested/review.vm"]

    def create_stackvm_flow(self, name, *, entry="decide", agent_name=None):
        self.create_flow_calls.append((name, entry, agent_name))
        path = self.workspace_root / ".pocketcode" / "flows" / f"{name}.md"
        agent = None
        if agent_name:
            parts = [part for part in agent_name.split(".") if part]
            group = parts[0]
            relative_parts = parts[1:] or [group]
            agent_dir = self.workspace_root / ".pocketcode" / f"agent.{group}"
            if len(relative_parts) > 1:
                agent_dir = agent_dir.joinpath(*relative_parts[:-1])
            agent = {
                "name": agent_name,
                "flow": name,
                "path": agent_dir / f"{relative_parts[-1]}.agent.md",
            }
        return {"name": name, "path": path, "entry": entry, "agent": agent}

    def create_stackvm_script(self, name, *, entry="main"):
        self.create_script_calls.append((name, entry))
        return {"name": name, "path": self.workspace_root / ".pocketcode" / "vm" / f"{name}.vm", "entry": entry}

    def create_stackvm_agent(self, name, *, flow_name):
        self.create_agent_calls.append((name, flow_name))
        parts = [part for part in name.split(".") if part]
        group = parts[0]
        relative_parts = parts[1:] or [group]
        agent_dir = self.workspace_root / ".pocketcode" / f"agent.{group}"
        if len(relative_parts) > 1:
            agent_dir = agent_dir.joinpath(*relative_parts[:-1])
        return {"name": name, "flow": flow_name, "path": agent_dir / f"{relative_parts[-1]}.agent.md"}

    def inspect_stackvm_target(self, kind, target, *, entry=None):
        self.inspect_calls.append((kind, target, entry))
        return {
            "target_kind": kind,
            "name": target,
            "path": self.workspace_root / ".pocketcode" / ("vm" if kind == "script" else "flows") / target,
            "flow": "resource_root.pocketcode.vm_review" if kind == "agent" else None,
            "agent": "review.safe" if kind == "agent" else None,
            "execution_mode": "vm",
            "vm_entry": entry or "decide",
            "source_files": [str(self.workspace_root / ".pocketcode" / "vm" / "router.vm")],
            "token_count": 5,
            "warning_count": 1,
            "warnings": [
                {
                    "code": "manual-tool-loop",
                    "location": "line 1, cols 1-10",
                    "message": "Prefer tool-once.",
                }
            ],
            "expanded_source": "[ \"done\" answer ] \"decide\" define",
            "source": "[ \"done\" answer ] \"decide\" define",
        }

    def update_stackvm_script(self, target, *, source_text):
        self.update_script_calls.append((target, source_text))
        return {"name": target, "path": self.workspace_root / ".pocketcode" / "vm" / target, "warnings": []}

    def update_markdown_asset(self, kind, target, *, markdown_text):
        self.update_markdown_calls.append((kind, target, markdown_text))
        return {"name": target, "path": self.workspace_root / ".pocketcode" / f"{kind}s" / f"{target}.md"}

    def run_stackvm_target(self, kind, target, *, request="", entry=None, debug=False, auto_confirm_tools=True):
        self.run_calls.append(
            {
                "kind": kind,
                "target": target,
                "request": request,
                "entry": entry,
                "debug": debug,
                "auto_confirm_tools": auto_confirm_tools,
            }
        )
        return {
            "output": "stackvm output",
            "error_message": None,
            "run_summary": {"vm_validation_warning_count": 1},
            "tool_history": [{"tool": "core.read_file"}],
            "trace_count": 2,
            "trace": [
                {"op": "push-literal", "value": "hello", "stack": ["hello"]},
                {"op": "word", "word": "answer", "stack": []},
            ],
            "last_vm_expanded_source": "[ \"hello\" answer ]",
            "last_vm_source": "[ \"hello\" answer ]",
        }


class TestCommandHandlerParsing:
    def test_universal_command_suggestions_exclude_textual_only_commands(self):
        suggestions = list_command_suggestions(_EngineStub())

        assert "/help" in suggestions
        assert "/agent" in suggestions
        assert "/stackvm" in suggestions
        assert "/copy" not in suggestions
        assert "/copy-all" not in suggestions
        assert "/view" not in suggestions

    def test_textual_command_suggestions_include_view_commands(self):
        suggestions = list_command_suggestions(_EngineStub(), interface_name="textual")

        assert "/view" in suggestions
        assert "/view switch run" in suggestions

    def test_command_suggestions_include_exported_provider_commands(self):
        engine = _ProviderCommandEngineStub(
            provider=_ProviderStub(
                CommandSpec(
                    name="memory.compact",
                    acp_action="memory.compact",
                    owner="root",
                    visibility="exported",
                )
            )
        )

        suggestions = list_command_suggestions(engine)

        assert "/memory.compact" in suggestions

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

    def test_unknown_command_falls_through_to_provider_dispatch(self, capsys):
        engine = _ProviderCommandEngineStub(
            provider=_ProviderStub(
                CommandSpec(
                    name="memory.compact",
                    acp_action="memory.compact",
                    owner="root",
                    visibility="exported",
                ),
                result=CommandResult(handled=True, output="memory compacted"),
            )
        )
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }

        handle_command("/memory.compact now", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert "memory compacted" in captured.out
        assert "Unknown command" not in captured.out

    def test_provider_permission_error_is_reported(self, capsys):
        engine = _ProviderCommandEngineStub(permission_error=PermissionError("missing capability"))
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }

        handle_command("/memory.compact", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert "Permission denied: missing capability" in captured.out

    def test_removed_asset_commands_report_unknown_command(self, tmp_path, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }

        handle_command("/asset list flow", engine=_EngineStub(), cli_context=cli_context)

        captured = capsys.readouterr()
        assert "Unknown command: /asset" in captured.out

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
        assert "Selected flow: core.react" in captured.out
        assert "Runtime Steps: 0" in captured.out
        assert "workflow" not in captured.out.lower()

    def test_debug_command_uses_debug_runner_callback(self, capsys):
        runner = _DebugRunnerRecorder()
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
            "interface": "basic",
            "debug_request_runner": runner,
        }

        handle_command(
            "/debug inspect the active agent",
            engine=_EngineStub(),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert runner.calls == ["inspect the active agent"]
        assert "debugged response" in captured.out

    def test_debug_command_reports_scope_without_runner(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
            "interface": "textual",
        }

        handle_command(
            "/debug inspect the active agent",
            engine=_EngineStub(),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "not available in this interface" in captured.out

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
        assert "VM Validation Warnings: manual-tool-loop, manual-prompt-route" in captured.out
        assert "Runtime Steps: 2" in captured.out
        assert "Runtime Effects: 2" in captured.out
        assert "Last Runtime Effect: call_tool" in captured.out

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
        assert "VM Validation Warnings: manual-tool-loop, manual-prompt-route" in captured.out
        assert "- manual-tool-loop (line 4, cols 1-12): Prefer tool-once." in captured.out
        assert "- manual-prompt-route (line 9, cols 5-22): Prefer prompt-route." in captured.out
        assert "1. agent_turn (completed) [12.0ms] Transition: call_tool" in captured.out
        assert "details: {'agent': 'core.react'}" in captured.out

    def test_status_steps_outputs_step_trace_without_verbose_details(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }

        handle_command(
            "/status steps",
            engine=_WarningStatusEngineStub(),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "Step Trace:" in captured.out
        assert "1. agent_turn (completed) [12.0ms] Transition: call_tool" in captured.out
        assert "details:" not in captured.out

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
        assert "breaks=1" in captured.out
        assert "Earlier work" in captured.out
        assert "breaks=2" in captured.out

    def test_session_show_reports_active_session(self, capsys):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command("/session show", engine=_SessionCommandEngineStub(), cli_context=cli_context)

        captured = capsys.readouterr()
        assert "Session:" in captured.out
        assert "session-1" in captured.out
        assert "First session" in captured.out
        assert "Debugger Breakpoints: 1" in captured.out
        assert "until node review" in captured.out

    def test_session_show_can_inspect_saved_session_breakpoints(self, capsys):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command("/session show session-2", engine=_SessionCommandEngineStub(), cli_context=cli_context)

        captured = capsys.readouterr()
        assert "session-2" in captured.out
        assert "Earlier work" in captured.out
        assert "Debugger Breakpoints: 2" in captured.out
        assert "until tool core.write_file" in captured.out

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

    def test_session_clear_breakpoints_requires_confirmation(self, capsys):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
        engine = _SessionCommandEngineStub()

        handle_command("/session clear-breakpoints session-2", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert engine.cleared_breakpoints == []
        assert "requires --yes" in captured.out

    def test_session_clear_breakpoints_reports_cleared_count(self, capsys):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
        engine = _SessionCommandEngineStub()

        handle_command("/session clear-breakpoints session-2 --yes", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert engine.cleared_breakpoints == ["session-2"]
        assert "Cleared 2 debugger breakpoint(s) from session: session-2" in captured.out

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
        assert "resource_root.pocketcode.review" in captured.out

    def test_agent_command_no_longer_falls_back_to_flow_selection(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }
        engine = _FlowSelectionEngineStub()

        handle_command(
            "/agent coder.coder",
            engine=engine,
            cli_context=cli_context,
        )

        assert engine.set_flow_calls == []
        captured = capsys.readouterr()
        assert "Unknown /agent subcommand: coder.coder" in captured.out

    def test_stackvm_list_prints_flows_and_scripts(self, capsys, tmp_path):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command("/stackvm list", engine=_StackVmCommandEngineStub(tmp_path), cli_context=cli_context)

        captured = capsys.readouterr()
        assert "resource_root.pocketcode.vm_review" in captured.out
        assert "router.vm" in captured.out

    def test_stackvm_create_flow_supports_entry_and_agent(self, capsys, tmp_path):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
        engine = _StackVmCommandEngineStub(tmp_path)

        handle_command(
            "/stackvm create flow vm_triage --entry route --agent review.safe",
            engine=engine,
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert engine.create_flow_calls == [("vm_triage", "route", "review.safe")]
        assert "Created StackVM flow 'vm_triage'" in captured.out

    def test_stackvm_inspect_prints_warning_and_expanded_source(self, capsys, tmp_path):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/stackvm inspect script router.vm --entry decide",
            engine=_StackVmCommandEngineStub(tmp_path),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "manual-tool-loop" in captured.out
        assert "Expanded StackVM:" in captured.out

    def test_stackvm_alter_script_uses_source_file(self, capsys, tmp_path):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
        engine = _StackVmCommandEngineStub(tmp_path)
        source_file = tmp_path / "router.vm"
        source_file.write_text("[ \"updated\" answer ]\n", encoding="utf-8")

        handle_command(
            f"/stackvm alter script router.vm {source_file}",
            engine=engine,
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert engine.update_script_calls == [("router.vm", "[ \"updated\" answer ]\n")]
        assert "Updated StackVM script" in captured.out

    def test_stackvm_debug_prints_trace(self, capsys, tmp_path):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}
        engine = _StackVmCommandEngineStub(tmp_path)

        handle_command(
            '/stackvm debug script router.vm --input "hello"',
            engine=engine,
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert engine.run_calls == [
            {
                "kind": "script",
                "target": "router.vm",
                "request": "hello",
                "entry": None,
                "debug": True,
                "auto_confirm_tools": True,
            }
        ]
        assert "Trace:" in captured.out
        assert "push-literal" in captured.out

    def test_flow_shortcut_alias_is_removed(self, capsys):
        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
        }

        handle_command(
            "/fl core.react",
            engine=_EngineStub(),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "Unknown command: /fl" in captured.out


class TestAgentCommands:
    def test_agent_list_hides_synthesised_flow_defaults(self, capsys):
        engine = _AgentListingEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent list",
            engine=engine,
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "core.react" not in captured.out
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

    def test_agent_mutation_commands_are_removed(self, capsys):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent clone coder.safe coder.clone",
            engine=_EditableProfileEngineStub(),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "Agent mutation commands were removed from the CLI" in captured.out


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

    def test_skill_enable_reports_removed_cli_mutation(self, capsys):
        engine = _ModeSkillEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command("/skill enable python-testing", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert "Skill mutation commands were removed from the CLI" in captured.out

    def test_skill_show_prints_provided_tools(self, capsys):
        engine = _ModeSkillEngineStub()
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command("/skill show python-testing", engine=engine, cli_context=cli_context)

        captured = capsys.readouterr()
        assert "Skill: python-testing" in captured.out
        assert "skill.python_testing.run_pytest" in captured.out

    def test_agent_tools_reports_removed_cli_mutation(self, capsys):
        cli_context = {"files": set(), "folders": set(), "urls": set(), "snippets": {}}

        handle_command(
            "/agent tools coder.safe all",
            engine=_EditableProfileEngineStub(),
            cli_context=cli_context,
        )

        captured = capsys.readouterr()
        assert "Agent mutation commands were removed from the CLI" in captured.out


class TestWorkspaceCanonicalToolImports:
    def test_workspace_git_tool_loads_from_flat_resource_root(self):
        from pocketcode.core.workspace_module_loader import load_workspace_module

        workspace_git = load_workspace_module(".pocketcode", "workspace_git.git.tool.py")

        assert "workspace_loader" in workspace_git.GitStatusTool.__module__

    def test_workspace_context_tool_loads_from_flat_resource_root(self):
        from pocketcode.core.workspace_module_loader import load_workspace_module

        workspace_context = load_workspace_module(
            ".pocketcode",
            "workspace_context.context_elephant_store_tools.tool.py",
        )

        assert workspace_context.ReadContextElephantStoreFileTool.__name__ == "ReadContextElephantStoreFileTool"
