from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from pocketcode.core.engine import PocketCodeEngine
from pocketcode.core.session_manager import SessionManager
from pocketcode.core.agent_profile_manager import _normalize_agent_commands
from pocketcode.core.command_runtime import CommandResult


def _build_engine(tmp_path: Path) -> PocketCodeEngine:
    engine = PocketCodeEngine.__new__(PocketCodeEngine)
    engine._config = {}
    engine._runtime_config = {}
    engine._workspace_root = tmp_path
    engine._session_manager = SessionManager(tmp_path)
    engine.active_session_id = None
    engine.active_session_title = None
    engine.active_session_loaded_from_history = False
    engine.active_agent_profile = None
    engine.current_agent = None
    engine.global_llm_override = None
    engine.agent_llm_overrides = {}
    engine.handoff_llm_overrides = {}
    engine.config_llm_overrides = {}
    engine.default_llm_profile = "default"
    engine.session_profile_overrides = {}
    engine.session_global_skills_override = None
    engine.session_confirmation_overrides = {
        "default_policy": None,
        "tool_policies": {},
        "agent_policies": {},
    }
    engine.session_debugger_breakpoints = []
    engine.enabled_skills = []
    engine._tool_confirmation_config = {
        "default_policy": "confirm",
        "tool_policies": {},
        "agent_policies": {},
    }
    engine.last_run_summary = {}
    engine._configured_enabled_skills = lambda profile_name=None: []
    engine.get_active_skills = lambda: []
    engine._normalize_agent_key_for_persistence = lambda value: value
    engine._copy_session_profile_overrides = lambda: dict(engine.session_profile_overrides)
    engine._normalize_session_confirmation_overrides = lambda value: dict(value or {})
    engine._copy_session_confirmation_overrides = lambda: dict(engine.session_confirmation_overrides)
    engine._copy_session_debugger_breakpoints = lambda: list(engine.session_debugger_breakpoints)
    engine._normalize_skill_names = lambda values, strict=False: list(values or [])
    engine._normalize_session_profile_overrides = lambda raw: dict(raw or {})
    engine.replace_session_confirmation_overrides = lambda value: setattr(
        engine,
        "session_confirmation_overrides",
        dict(value or {}),
    )
    engine.set_global_llm_override = lambda value: setattr(engine, "global_llm_override", value)
    engine._refresh_runtime_components = lambda: None
    engine.set_active_agent_profile = lambda name: setattr(engine, "active_agent_profile", None)
    engine.set_agent = lambda name: setattr(engine, "current_agent", name)
    engine._named_agent_profiles = {}
    engine.get_agent_profile = lambda name=None: (
        engine.active_agent_profile
        if name is None
        else engine._named_agent_profiles.get(name)
    )
    engine._active_agent_local_handlers = {}
    engine.get_active_agent_local_command_handlers = lambda profile=None: dict(engine._active_agent_local_handlers)
    return engine


class TestCommandRuntimeServices:
    def test_root_command_context_gets_default_root_capabilities(self, tmp_path: Path):
        engine = _build_engine(tmp_path)

        root_ctx = engine.build_command_context()
        subagent_ctx = engine.build_command_context(caller_agent="memory.compactor")

        assert "memory.compact" in root_ctx.capabilities
        assert "checkpoint.restore" in root_ctx.capabilities
        assert subagent_ctx.capabilities == set()

    def test_normalize_agent_commands_parses_declarative_aliases(self):
        commands = _normalize_agent_commands(
            [
                {
                    "name": "compact-now",
                    "target": "memory compact 1",
                    "visibility": "exported",
                    "capabilities": ["memory.compact"],
                    "payload_schema": {"type": "object", "properties": {"mode": {"type": "string"}}},
                    "result_schema": {"type": "object", "properties": {"summary": {"type": "string"}}},
                    "policy": {"confirmation": "confirm"},
                }
            ],
            field_name="review.agent.md",
        )

        assert len(commands) == 1
        assert commands[0].name == "compact-now"
        assert commands[0].target == "memory compact 1"
        assert commands[0].capabilities == ["memory.compact"]
        assert commands[0].payload_schema["type"] == "object"
        assert commands[0].result_schema["properties"]["summary"]["type"] == "string"
        assert commands[0].policy == {"confirmation": "confirm"}

    def test_trim_session_memory_keeps_tail(self, tmp_path: Path):
        engine = _build_engine(tmp_path)
        record = engine._session_manager.create_session(
            state={
                "transcript": [
                    {"role": "user", "content": "one"},
                    {"role": "assistant", "content": "two"},
                    {"role": "user", "content": "three"},
                ]
            }
        )
        engine.active_session_id = record.session_id
        engine.active_session_title = record.title

        result = engine.trim_session_memory(keep_last=2)
        updated = engine._session_manager.load_session(record.session_id)

        assert result == {"session_id": record.session_id, "kept": 2, "removed": 1}
        assert [entry.content for entry in updated.transcript] == ["two", "three"]

    def test_compact_session_memory_replaces_older_entries_with_summary(self, tmp_path: Path):
        engine = _build_engine(tmp_path)
        record = engine._session_manager.create_session(
            state={
                "transcript": [
                    {"role": "user", "content": "alpha"},
                    {"role": "assistant", "content": "beta"},
                    {"role": "user", "content": "gamma"},
                ]
            }
        )
        engine.active_session_id = record.session_id
        engine.active_session_title = record.title

        result = engine.compact_session_memory(keep_last=1)
        updated = engine._session_manager.load_session(record.session_id)

        assert result["session_id"] == record.session_id
        assert result["compacted_entries"] == 2
        assert len(updated.transcript) == 2
        assert updated.transcript[0].role == "system"
        assert "compacted 2 earlier transcript entries" in updated.transcript[0].content
        assert updated.transcript[1].content == "gamma"

    def test_checkpoint_save_list_and_restore_round_trip(self, tmp_path: Path):
        engine = _build_engine(tmp_path)
        record = engine._session_manager.create_session(
            state={
                "active_agent": "core.react",
                "global_llm_profile": "fast",
                "transcript": [
                    {"role": "user", "content": "before"},
                    {"role": "assistant", "content": "state"},
                ],
            }
        )
        engine.active_session_id = record.session_id
        engine.active_session_title = record.title
        engine.current_agent = "core.react"
        engine.global_llm_override = "fast"

        saved = engine.save_checkpoint("baseline")
        checkpoint_file = tmp_path / ".pocketstate" / "checkpoints" / "baseline.json"
        payload = json.loads(checkpoint_file.read_text(encoding="utf-8"))

        assert saved["name"] == "baseline"
        assert checkpoint_file.exists() is True
        assert payload["state"]["active_agent"] == "core.react"
        assert payload["transcript"][0]["content"] == "before"

        engine._session_manager.update_session(
            record.session_id,
            transcript=[{"role": "system", "content": "mutated"}],
        )

        listed = engine.list_checkpoints()
        restored = engine.restore_checkpoint("baseline")
        updated = engine._session_manager.load_session(record.session_id)

        assert listed[0]["name"] == "baseline"
        assert restored["name"] == "baseline"
        assert restored["transcript_entries"] == 2
        assert [entry.content for entry in updated.transcript] == ["before", "state"]

    def test_subagent_context_must_supply_memory_capability(self, tmp_path: Path):
        engine = _build_engine(tmp_path)
        record = engine._session_manager.create_session(
            state={"transcript": [{"role": "user", "content": "one"}]}
        )
        engine.active_session_id = record.session_id
        engine.active_session_title = record.title

        denied_ctx = engine.build_command_context(caller_agent="memory.compactor")

        try:
            engine._invoke_memory_command(["trim", "1"], denied_ctx)
        except PermissionError as exc:
            assert "memory.trim" in str(exc)
        else:
            raise AssertionError("Expected PermissionError for subagent without memory.trim capability.")

        allowed_ctx = engine.build_command_context(
            caller_agent="memory.compactor",
            capabilities={"memory.trim"},
        )
        result = engine._invoke_memory_command(["trim", "1"], allowed_ctx)

        assert result.handled is True
        assert "Memory trimmed:" in str(result.output or "")

    def test_subagent_context_must_supply_checkpoint_restore_capability(self, tmp_path: Path):
        engine = _build_engine(tmp_path)
        record = engine._session_manager.create_session(
            state={"transcript": [{"role": "user", "content": "before"}]}
        )
        engine.active_session_id = record.session_id
        engine.active_session_title = record.title
        engine.save_checkpoint("baseline")

        denied_ctx = engine.build_command_context(caller_agent="checkpoint.agent")

        try:
            engine._invoke_checkpoint_command(["restore", "baseline"], denied_ctx)
        except PermissionError as exc:
            assert "checkpoint.restore" in str(exc)
        else:
            raise AssertionError("Expected PermissionError for subagent without checkpoint.restore capability.")

        allowed_ctx = engine.build_command_context(
            caller_agent="checkpoint.agent",
            capabilities={"checkpoint.restore"},
        )
        result = engine._invoke_checkpoint_command(["restore", "baseline"], allowed_ctx)

        assert result.handled is True
        assert "Checkpoint restored:" in str(result.output or "")

    def test_active_agent_provider_exports_declared_command_aliases(self, tmp_path: Path):
        engine = _build_engine(tmp_path)
        record = engine._session_manager.create_session(
            state={
                "transcript": [
                    {"role": "user", "content": "alpha"},
                    {"role": "assistant", "content": "beta"},
                ]
            }
        )
        engine.active_session_id = record.session_id
        engine.active_session_title = record.title
        engine.active_agent_profile = SimpleNamespace(
            name="review.safe",
            commands=_normalize_agent_commands(
                [
                    {
                        "name": "compact-now",
                        "target": "memory compact 1",
                        "visibility": "exported",
                        "description": "Compact memory now.",
                        "capabilities": ["memory.compact"],
                        "payload_schema": {"type": "object"},
                        "result_schema": {"type": "object"},
                        "policy": {"confirmation": "confirm"},
                    }
                ],
                field_name="review.agent.md",
            ),
        )

        provider = engine.get_active_agent_command_provider()
        result = engine.invoke_registered_command("/compact-now", [], cli_context={})
        updated = engine._session_manager.load_session(record.session_id)

        assert provider is not None
        assert [spec.name for spec in provider.list_commands(visibility="exported")] == ["compact-now"]
        assert provider.list_commands(visibility="exported")[0].payload_schema == {"type": "object"}
        assert provider.list_commands(visibility="exported")[0].result_schema == {"type": "object"}
        assert provider.list_commands(visibility="exported")[0].policy == {"confirmation": "confirm"}
        assert result is not None and result.handled is True
        assert "Memory compacted:" in str(result.output or "")
        assert len(updated.transcript) == 2
        assert updated.transcript[0].role == "system"

    def test_agent_command_can_target_another_agents_delegated_command(self, tmp_path: Path):
        engine = _build_engine(tmp_path)
        record = engine._session_manager.create_session(
            state={"transcript": [{"role": "user", "content": "one"}]}
        )
        engine.active_session_id = record.session_id
        engine.active_session_title = record.title
        review_profile = SimpleNamespace(
            name="review.safe",
            commands=_normalize_agent_commands(
                [
                    {
                        "name": "compact-via-review",
                        "target": {
                            "kind": "agent_command",
                            "agent": "review.worker",
                            "command": "trim-delegated",
                            "visibility": "delegated",
                        },
                        "visibility": "exported",
                    }
                ],
                field_name="review.agent.md",
            ),
        )
        worker_profile = SimpleNamespace(
            name="review.worker",
            commands=_normalize_agent_commands(
                [
                    {
                        "name": "trim-delegated",
                        "target": "memory trim 1",
                        "visibility": "delegated",
                        "capabilities": ["memory.trim"],
                    }
                ],
                field_name="worker.agent.md",
            ),
        )
        engine.active_agent_profile = review_profile
        engine._named_agent_profiles = {
            "review.safe": review_profile,
            "review.worker": worker_profile,
        }

        result = engine.invoke_registered_command("/compact-via-review", [], cli_context={})

        assert result is not None and result.handled is True
        assert "Memory trimmed:" in str(result.output or "")

    def test_agent_command_can_target_local_handler(self, tmp_path: Path):
        engine = _build_engine(tmp_path)
        engine.active_agent_profile = SimpleNamespace(
            name="review.safe",
            commands=_normalize_agent_commands(
                [
                    {
                        "name": "local-review",
                        "target": {
                            "kind": "local_handler",
                            "handler": "review_local",
                        },
                        "visibility": "exported",
                        "payload_schema": {
                            "type": "object",
                            "required": ["mode"],
                            "properties": {
                                "mode": {"type": "string"},
                                "limit": {"type": "integer"},
                            },
                        },
                        "result_schema": {
                            "type": "object",
                            "required": ["payload"],
                            "properties": {
                                "payload": {"type": "object"},
                            },
                        },
                    }
                ],
                field_name="review.agent.md",
            ),
        )
        engine._active_agent_local_handlers = {
            "review_local": lambda args, ctx, declaration, invocation: CommandResult(
                handled=True,
                output=(
                    f"local handler ran with {len(args)} args for {declaration.name} "
                    f"via {invocation.command_name}"
                ),
                data={"payload": dict(invocation.payload)},
                metadata={"caller_agent": invocation.caller_agent},
            )
        }

        result = engine.invoke_active_agent_command(
            "local-review",
            ["extra"],
            cli_context={},
            payload={"mode": "strict", "limit": 2},
            visibility="exported",
        )

        assert result is not None
        assert result.handled is True
        assert result.output == "local handler ran with 1 args for local-review via local-review"
        assert result.data == {"payload": {"mode": "strict", "limit": 2}}
        assert result.metadata["caller_agent"] is None

    def test_agent_command_payload_schema_rejects_invalid_payload(self, tmp_path: Path):
        engine = _build_engine(tmp_path)
        engine.active_agent_profile = SimpleNamespace(
            name="review.safe",
            commands=_normalize_agent_commands(
                [
                    {
                        "name": "local-review",
                        "target": {
                            "kind": "local_handler",
                            "handler": "review_local",
                        },
                        "visibility": "exported",
                        "payload_schema": {
                            "type": "object",
                            "required": ["mode"],
                            "properties": {
                                "mode": {"type": "string"},
                                "limit": {"type": "integer"},
                            },
                        },
                    }
                ],
                field_name="review.agent.md",
            ),
        )
        engine._active_agent_local_handlers = {
            "review_local": lambda args, ctx, declaration, invocation: CommandResult(
                handled=True,
                output="should not run",
            )
        }

        try:
            engine.invoke_active_agent_command(
                "local-review",
                [],
                cli_context={},
                payload={"mode": 1, "limit": "bad"},
                visibility="exported",
            )
        except ValueError as exc:
            assert "payload.mode" in str(exc)
        else:
            raise AssertionError("Expected payload validation to reject invalid types.")

    def test_agent_command_result_schema_rejects_invalid_result_data(self, tmp_path: Path):
        engine = _build_engine(tmp_path)
        engine.active_agent_profile = SimpleNamespace(
            name="review.safe",
            commands=_normalize_agent_commands(
                [
                    {
                        "name": "local-review",
                        "target": {
                            "kind": "local_handler",
                            "handler": "review_local",
                        },
                        "visibility": "exported",
                        "result_schema": {
                            "type": "object",
                            "required": ["summary"],
                            "properties": {
                                "summary": {"type": "string"},
                            },
                        },
                    }
                ],
                field_name="review.agent.md",
            ),
        )
        engine._active_agent_local_handlers = {
            "review_local": lambda args, ctx, declaration, invocation: CommandResult(
                handled=True,
                output="bad result",
                data={"summary": 123},
            )
        }

        try:
            engine.invoke_active_agent_command(
                "local-review",
                [],
                cli_context={},
                visibility="exported",
            )
        except ValueError as exc:
            assert "result.data.summary" in str(exc)
        else:
            raise AssertionError("Expected result validation to reject invalid result data.")

    def test_active_agent_command_specs_filter_by_visibility(self, tmp_path: Path):
        engine = _build_engine(tmp_path)
        engine.active_agent_profile = SimpleNamespace(
            name="review.safe",
            commands=_normalize_agent_commands(
                [
                    {"name": "exported-cmd", "target": "memory show", "visibility": "exported"},
                    {"name": "delegated-cmd", "target": "checkpoint list", "visibility": "delegated"},
                    {"name": "private-cmd", "target": "memory show", "visibility": "private"},
                ],
                field_name="review.agent.md",
            ),
        )

        exported = engine.list_active_agent_command_specs(visibility="exported")
        delegated = engine.list_active_agent_command_specs(visibility="delegated")
        private = engine.list_active_agent_command_specs(visibility="private")

        assert [spec.name for spec in exported] == ["exported-cmd"]
        assert [spec.name for spec in delegated] == ["delegated-cmd"]
        assert [spec.name for spec in private] == ["private-cmd"]

    def test_delegated_agent_command_can_be_invoked_without_being_exported(self, tmp_path: Path):
        engine = _build_engine(tmp_path)
        record = engine._session_manager.create_session(
            state={"transcript": [{"role": "user", "content": "one"}]}
        )
        engine.active_session_id = record.session_id
        engine.active_session_title = record.title
        engine.active_agent_profile = SimpleNamespace(
            name="review.safe",
            commands=_normalize_agent_commands(
                [
                    {
                        "name": "trim-delegated",
                        "target": "memory trim 1",
                        "visibility": "delegated",
                        "capabilities": ["memory.trim"],
                    }
                ],
                field_name="review.agent.md",
            ),
        )

        exported_provider = engine.get_active_agent_command_provider()
        direct = engine.invoke_registered_command("/trim-delegated", [], cli_context={})
        delegated = engine.invoke_active_agent_command(
            "trim-delegated",
            [],
            cli_context={},
            caller_agent="parent.agent",
            capabilities=set(),
            visibility="delegated",
        )

        assert exported_provider is None
        assert direct is None
        assert delegated is not None and delegated.handled is True
        assert "Memory trimmed:" in str(delegated.output or "")

    def test_private_agent_command_requires_private_visibility_lookup(self, tmp_path: Path):
        engine = _build_engine(tmp_path)
        record = engine._session_manager.create_session(
            state={"transcript": [{"role": "user", "content": "one"}]}
        )
        engine.active_session_id = record.session_id
        engine.active_session_title = record.title
        engine.active_agent_profile = SimpleNamespace(
            name="review.safe",
            commands=_normalize_agent_commands(
                [
                    {
                        "name": "compact-private",
                        "target": "memory compact 0",
                        "visibility": "private",
                        "capabilities": ["memory.compact"],
                    }
                ],
                field_name="review.agent.md",
            ),
        )

        delegated_lookup = engine.invoke_active_agent_command(
            "compact-private",
            [],
            cli_context={},
            caller_agent="review.safe",
            capabilities=set(),
            visibility="delegated",
        )
        private_lookup = engine.invoke_active_agent_command(
            "compact-private",
            [],
            cli_context={},
            caller_agent="review.safe",
            capabilities=set(),
            visibility="private",
        )

        assert delegated_lookup is None
        assert private_lookup is not None and private_lookup.handled is True
        assert "Memory compacted:" in str(private_lookup.output or "")
