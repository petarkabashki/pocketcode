from __future__ import annotations

import dataclasses
import logging
import copy
import importlib
import json
import sys
import shlex
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import yaml

from pocketcode.core.agent_manager import AgentManager
from pocketcode.config.loader import WORKSPACE_SETTINGS_FILENAME
from pocketcode.core.catalog_metadata import namespace_name_from_metadata, namespace_root_from_metadata
from pocketcode.core.markdown_profiles import (
    SkillDefinition,
    SkillManager,
    parse_markdown_front_matter,
)
from pocketcode.core.agent_runtime import AgentRuntime
from pocketcode.core.llm_router import LlmRouter
from pocketcode.core.namespace_registry import RegistryError
from pocketcode.core.workspace_catalog import WorkspaceCatalog
from pocketcode.core.prompt_loader import (
    coerce_str_list,
    is_prompt_reference,
    load_prompt_markdown,
    resolve_prompt_bundle,
    resolve_prompt_reference,
)
from pocketcode.core.reference_syntax import (
    normalize_prompt_source,
    normalize_registry_reference,
    parse_prompt_reference,
    parse_reference,
    validate_prompt_source,
    validate_registry_reference,
)
from pocketcode.core.run_handle import RunCancelledError, RunHandle
from pocketcode.core.runtime_observability import (
    build_runtime_observability_summary,
    initialize_runtime_observability,
    observe_runtime_event,
)
from pocketcode.core.runtime_models import AgentProfile, FlowDefinition
from pocketcode.core.resource_roots import primary_resource_root, resource_root_namespace
from pocketcode.core.runtime_storage import load_entry_history, normalize_entry_history, save_entry_history
from pocketcode.core.runtime_storage import checkpoint_storage_dir
from pocketcode.core.session_manager import SessionManager
from pocketcode.core.stackvm_expander import expand_stackvm_source
from pocketcode.core.stackvm_loader import load_stackvm_program_source
from pocketcode.core.stackvm_parser import parse_stackvm_source, serialize_stackvm_ast, tokenize_stackvm_source
from pocketcode.core.stackvm_validator import collect_stackvm_authoring_warnings, validate_stackvm_ast
from pocketcode.core.tool_runtime import ToolRuntime
from pocketcode.core.workspace_llm_profile_manager import WorkspaceLlmProfileManager
from pocketcode.core.markdown_assets import (
    compile_markdown_agent_definition,
    compile_markdown_flow_definition,
    compile_markdown_tool_definition,
    parse_markdown_asset_text_document,
)
from pocketcode.cli.debugger_commands import build_debugger_predicate_from_label
from pocketcode.core.command_runtime import (
    CommandContext,
    CommandInvocation,
    CommandProvider,
    CommandResult,
    CommandSpec,
    StaticCommandProvider,
    build_command_invocation,
)
from pocketcode.core.command_validation import validate_command_payload, validate_command_result_data

logger = logging.getLogger(__name__)
_UNSET = object()
DEFAULT_ROOT_COMMAND_CAPABILITIES = frozenset(
    {
        "memory.read",
        "memory.trim",
        "memory.compact",
        "checkpoint.read",
        "checkpoint.write",
        "checkpoint.restore",
    }
)


class PocketCodeEngine:
    def __init__(self, config: Dict[str, Any], workspace_root: str | Path):
        self._config = config
        self._workspace_root = Path(workspace_root).resolve()
        self._runtime_config = config.get("runtime", {}) if isinstance(config, dict) else {}
        self._llm_config = config.get("llm", {}) if isinstance(config, dict) else {}
        if not isinstance(self._llm_config, dict):
            self._llm_config = {}
        self._tool_confirmation_config = self._build_tool_confirmation_config()

        self._catalog = WorkspaceCatalog(config=config, workspace_root=self._workspace_root)
        self._catalog.load()

        # T011: instantiate AgentManager after the catalog is loaded.
        self._agent_profile_manager = AgentManager(self._workspace_root, prompt_registry=self._catalog.prompts)
        self._agent_profile_manager.load(dict(self._catalog.agents))
        self._skill_manager = SkillManager(
            self._workspace_root,
            tool_registry=self._catalog.tools,
            prompt_registry=self._catalog.prompts,
        )
        self._skill_manager.load()
        self._session_manager = SessionManager(self._workspace_root, config=self._config)
        self._workspace_llm_profile_manager = WorkspaceLlmProfileManager(self._workspace_root)
        self._workspace_llm_profile_manager.load()
        self._validate_loaded_reference_surfaces()
        self.active_agent_profile = None  # type: ignore[assignment]  # AgentProfile | None
        self.session_profile_overrides: Dict[str, Dict[str, Any]] = {}
        self.session_global_skills_override: List[str] | None = None
        self.enabled_skills = self._configured_enabled_skills()

        self._llm_router = LlmRouter(config=config, resource_root_llm_profiles=self._merged_llm_profiles())
        self._tool_runtime = self._build_tool_runtime()
        self._agent_runtime = AgentRuntime(
            catalog=self._catalog,
            llm_router=self._llm_router,
            tool_runtime=self._tool_runtime,
            runtime_config=self._runtime_config,
        )
        self._agent_tools_cache: Dict[str, List[str]] = {}

        self.default_llm_profile = (
            self._llm_config.get("default_profile")
            or self._llm_router.default_profile_name
        )
        self.config_llm_overrides = self._build_llm_overrides_config()

        self.current_agent = self._normalize_agent_name(self._runtime_config.get("default_agent"))
        self.global_llm_override = None  # type: ignore[assignment]
        self.agent_llm_overrides: Dict[str, str] = {}
        self.handoff_llm_overrides: Dict[str, str] = {}
        self.auto_confirm_tools = bool(self._runtime_config.get("auto_confirm_tools", False))
        self.session_confirmation_overrides: Dict[str, Any] = {
            "default_policy": None,
            "tool_policies": {},
            "agent_policies": {},
        }
        self.session_debugger_breakpoints: List[str] = []
        self.active_session_id: str | None = None
        self.active_session_title: str | None = None
        self.active_session_loaded_from_history = False
        self.last_run_summary: Dict[str, Any] = {
            "agent_path": [],
            "current_agent": self.current_agent,
            "current_llm_profile": None,
            "current_llm_model": None,
            "llm_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "llm_cost_usd": 0.0,
            "context_stats": {"files": 0, "folders": 0, "urls": 0, "snippets": 0, "snippet_chars": 0},
            "runtime_event_count": 0,
            "step_count": 0,
            "steps": [],
        }

        self._validate_current_selections()
        self._restore_textual_selection_state()
        self._ensure_active_session()

    def build_command_context(
        self,
        cli_context: Dict[str, Any] | None = None,
        *,
        caller_agent: str | None = None,
        capabilities: set[str] | None = None,
    ) -> CommandContext:
        active_agent = self.active_agent_profile.name if self.active_agent_profile is not None else None
        cleaned_caller = str(caller_agent).strip() or None if caller_agent is not None else None
        resolved_capabilities = (
            set(capabilities)
            if capabilities is not None
            else (set(DEFAULT_ROOT_COMMAND_CAPABILITIES) if cleaned_caller is None else set())
        )
        return CommandContext(
            engine=self,
            cli_context=dict(cli_context or {}),
            caller_agent=cleaned_caller,
            active_agent=active_agent,
            session_id=getattr(self, "active_session_id", None),
            capabilities=resolved_capabilities,
        )

    def get_root_command_provider(self) -> CommandProvider | None:
        commands = [
            CommandSpec(
                name="memory",
                acp_action="memory.command",
                owner="root",
                visibility="exported",
                description="Manage active-session memory state.",
            ),
            CommandSpec(
                name="checkpoint",
                acp_action="checkpoint.command",
                owner="root",
                visibility="exported",
                description="Manage named runtime checkpoints.",
            ),
        ]
        return StaticCommandProvider(commands=commands, handler=self._invoke_root_command)

    def get_active_agent_command_provider(self) -> CommandProvider | None:
        exported_specs = self.list_active_agent_command_specs(visibility="exported")
        if not exported_specs:
            return None
        return StaticCommandProvider(commands=exported_specs, handler=self._invoke_active_agent_command)

    def get_active_agent_local_command_handlers(self, profile: Any | None = None) -> Dict[str, Any]:
        return {}

    def list_active_agent_command_specs(self, *, visibility: str | None = None) -> list[CommandSpec]:
        profile = getattr(self, "active_agent_profile", None)
        if profile is None:
            return []
        requested_visibility = str(visibility or "").strip().lower() or None
        commands = list(getattr(profile, "commands", []) or [])
        specs: list[CommandSpec] = []
        for command in commands:
            name = str(getattr(command, "name", "") or "").strip()
            target = str(getattr(command, "target", "") or "").strip()
            command_visibility = str(getattr(command, "visibility", "exported") or "exported").strip().lower() or "exported"
            if not name or not target:
                continue
            if requested_visibility is not None and command_visibility != requested_visibility:
                continue
            specs.append(
                CommandSpec(
                    name=name,
                    acp_action=f"agent.command.{name}",
                    owner=str(getattr(profile, "name", "active-agent") or "active-agent"),
                    visibility=command_visibility,
                    description=str(getattr(command, "description", "") or "").strip(),
                    required_capabilities=(),
                    payload_schema=dict(getattr(command, "payload_schema", {}) or {}),
                    result_schema=dict(getattr(command, "result_schema", {}) or {}),
                    policy=dict(getattr(command, "policy", {}) or {}),
                )
            )
        return specs

    def get_command_providers(self) -> list[CommandProvider]:
        providers: list[CommandProvider] = []
        active_provider = self.get_active_agent_command_provider()
        root_provider = self.get_root_command_provider()
        if active_provider is not None:
            providers.append(active_provider)
        if root_provider is not None and root_provider is not active_provider:
            providers.append(root_provider)
        return providers

    def authorize_command(self, spec: CommandSpec, ctx: CommandContext) -> None:
        required = {str(item).strip() for item in getattr(spec, "required_capabilities", ()) if str(item).strip()}
        if not required:
            return
        if required.issubset(set(ctx.capabilities)):
            return
        missing = sorted(required - set(ctx.capabilities))
        raise PermissionError(
            f"Command '{spec.name}' requires capabilities not available in this context: {', '.join(missing)}."
        )

    def invoke_registered_command(
        self,
        command_name: str,
        args: list[str],
        *,
        cli_context: Dict[str, Any] | None = None,
        caller_agent: str | None = None,
        capabilities: set[str] | None = None,
    ) -> CommandResult | None:
        normalized = str(command_name or "").strip().lstrip("/")
        if not normalized:
            return None
        ctx = self.build_command_context(cli_context, caller_agent=caller_agent, capabilities=capabilities)
        for provider in self.get_command_providers():
            commands = provider.list_commands(visibility="exported")
            spec = next((item for item in commands if item.name == normalized), None)
            if spec is None:
                continue
            self.authorize_command(spec, ctx)
            result = provider.invoke(normalized, list(args), ctx)
            return result if isinstance(result, CommandResult) else None
        return None

    def build_command_invocation(
        self,
        command_name: str,
        args: list[str],
        *,
        caller_agent: str | None = None,
        capabilities: set[str] | None = None,
        visibility: str | None = None,
        payload: Dict[str, Any] | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> CommandInvocation:
        active_agent = self.active_agent_profile.name if self.active_agent_profile is not None else None
        session_id = getattr(self, "active_session_id", None)
        resolved_capabilities = (
            set(capabilities)
            if capabilities is not None
            else (set(DEFAULT_ROOT_COMMAND_CAPABILITIES) if not str(caller_agent or "").strip() else set())
        )
        return build_command_invocation(
            command_name,
            args=args,
            caller_agent=caller_agent,
            active_agent=active_agent,
            session_id=session_id,
            visibility=visibility,
            capabilities=resolved_capabilities,
            payload=payload,
            metadata=metadata,
        )

    def _invoke_root_command(self, name: str, args: list[str], ctx: CommandContext) -> CommandResult:
        if name == "memory":
            return self._invoke_memory_command(args, ctx)
        if name == "checkpoint":
            return self._invoke_checkpoint_command(args, ctx)
        return CommandResult(handled=False)

    def _invoke_active_agent_command(self, name: str, args: list[str], ctx: CommandContext) -> CommandResult:
        return self.invoke_active_agent_command(
            name,
            args,
            cli_context=ctx.cli_context,
            caller_agent=ctx.caller_agent,
            capabilities=set(ctx.capabilities),
            visibility="exported",
        ) or CommandResult(handled=False)

    def invoke_active_agent_command(
        self,
        command_name: str,
        args: list[str],
        *,
        cli_context: Dict[str, Any] | None = None,
        caller_agent: str | None = None,
        capabilities: set[str] | None = None,
        visibility: str | None = None,
        payload: Dict[str, Any] | None = None,
        invocation: CommandInvocation | None = None,
    ) -> CommandResult | None:
        profile = getattr(self, "active_agent_profile", None)
        if profile is None:
            return None
        active_invocation = invocation or self.build_command_invocation(
            command_name,
            list(args),
            caller_agent=caller_agent,
            capabilities=capabilities,
            visibility=visibility,
            payload=payload,
        )
        normalized_name = str(active_invocation.command_name or "").strip().lstrip("/")
        if not normalized_name:
            return None
        ctx = self.build_command_context(
            cli_context,
            caller_agent=active_invocation.caller_agent,
            capabilities=set(active_invocation.capabilities),
        )
        requested_visibility = str(active_invocation.visibility or "").strip().lower() or None
        declaration = next(
            (
                command
                for command in list(getattr(profile, "commands", []) or [])
                if str(getattr(command, "name", "") or "").strip() == normalized_name
                and (
                    requested_visibility is None
                    or str(getattr(command, "visibility", "exported") or "exported").strip().lower() == requested_visibility
                )
            ),
            None,
        )
        if declaration is None:
            return None
        payload_schema = dict(getattr(declaration, "payload_schema", {}) or {})
        result_schema = dict(getattr(declaration, "result_schema", {}) or {})
        validate_command_payload(active_invocation.payload, payload_schema)
        target = str(getattr(declaration, "target", "") or "").strip()
        target_kind = str(getattr(declaration, "target_kind", "command") or "command").strip().lower() or "command"
        delegated_capabilities = set(ctx.capabilities)
        delegated_capabilities.update(
            str(item).strip() for item in list(getattr(declaration, "capabilities", []) or []) if str(item).strip()
        )
        if target_kind == "command":
            if not target:
                return None
            target_parts = shlex.split(target)
            if not target_parts:
                return None
            target_name = str(target_parts[0]).lstrip("/")
            if target_name == normalized_name:
                raise ValueError(f"Agent command '{normalized_name}' cannot target itself.")
            result = self.invoke_registered_command(
                f"/{target_name}",
                [*target_parts[1:], *list(args)],
                cli_context=ctx.cli_context,
                caller_agent=str(getattr(profile, "name", "") or "").strip() or "active-agent",
                capabilities=delegated_capabilities,
            )
            if isinstance(result, CommandResult):
                validate_command_result_data(result.data, result_schema)
                return result
            return CommandResult(handled=False)
        if target_kind == "agent_command":
            target_agent = str(getattr(declaration, "target_agent", "") or "").strip()
            target_visibility = str(getattr(declaration, "target_visibility", "") or "").strip().lower() or "delegated"
            if not target_agent or not target:
                return None
            if target_agent == str(getattr(profile, "name", "") or "").strip() and target == normalized_name:
                raise ValueError(f"Agent command '{normalized_name}' cannot target itself.")
            result = self.invoke_named_agent_command(
                target_agent,
                target,
                list(args),
                cli_context=ctx.cli_context,
                caller_agent=str(getattr(profile, "name", "") or "").strip() or "active-agent",
                capabilities=delegated_capabilities,
                visibility=target_visibility,
                payload=dict(active_invocation.payload),
                invocation=self.build_command_invocation(
                    target,
                    list(args),
                    caller_agent=str(getattr(profile, "name", "") or "").strip() or "active-agent",
                    capabilities=delegated_capabilities,
                    visibility=target_visibility,
                    payload=dict(active_invocation.payload),
                    metadata={
                        "source_agent_command": normalized_name,
                        "source_agent_profile": str(getattr(profile, "name", "") or "").strip() or None,
                    },
                ),
            )
            if isinstance(result, CommandResult):
                validate_command_result_data(result.data, result_schema)
                return result
            return CommandResult(handled=False)
        if target_kind == "local_handler":
            target_handler = str(getattr(declaration, "target_handler", "") or "").strip()
            if not target_handler:
                return None
            handlers = self.get_active_agent_local_command_handlers(profile)
            handler = handlers.get(target_handler) if isinstance(handlers, dict) else None
            if not callable(handler):
                raise ValueError(
                    f"Active agent command '{normalized_name}' references unknown local handler '{target_handler}'."
                )
            result = handler(
                list(args),
                ctx,
                declaration,
                active_invocation,
            )
            if isinstance(result, CommandResult):
                validate_command_result_data(result.data, result_schema)
                return result
            return CommandResult(handled=False)
        raise ValueError(f"Unsupported agent command target kind '{target_kind}'.")

    def invoke_named_agent_command(
        self,
        agent_name: str,
        command_name: str,
        args: list[str],
        *,
        cli_context: Dict[str, Any] | None = None,
        caller_agent: str | None = None,
        capabilities: set[str] | None = None,
        visibility: str | None = None,
        payload: Dict[str, Any] | None = None,
        invocation: CommandInvocation | None = None,
    ) -> CommandResult | None:
        target_name = str(agent_name or "").strip()
        if not target_name:
            return None
        getter = getattr(self, "get_agent_profile", None)
        if not callable(getter):
            return None
        target_profile = getter(target_name)
        if target_profile is None:
            return None
        original_profile = getattr(self, "active_agent_profile", None)
        try:
            self.active_agent_profile = target_profile
            return self.invoke_active_agent_command(
                command_name,
                args,
                cli_context=cli_context,
                caller_agent=caller_agent,
                capabilities=capabilities,
                visibility=visibility,
                payload=payload,
                invocation=invocation,
            )
        finally:
            self.active_agent_profile = original_profile

    def _invoke_memory_command(self, args: list[str], ctx: CommandContext) -> CommandResult:
        subcommand = str(args[0] if args else "show").strip().lower()
        if subcommand in {"show", "status"}:
            self._require_command_capability(ctx, "memory.read", command_name="memory show")
            info = self.get_active_session_info()
            details = self.get_saved_session_details(info.get("session_id"))
            return CommandResult(
                handled=True,
                output=(
                    "Memory:\n"
                    f"  Session: {details.get('session_id')}\n"
                    f"  Transcript Entries: {details.get('transcript_entries', 0)}"
                ),
            )
        if subcommand == "trim":
            self._require_command_capability(ctx, "memory.trim", command_name="memory trim")
            keep_last = self._parse_positive_int_arg(args[1] if len(args) > 1 else None, default=20)
            result = self.trim_session_memory(keep_last=keep_last)
            return CommandResult(
                handled=True,
                output=(
                    "Memory trimmed:\n"
                    f"  Session: {result['session_id']}\n"
                    f"  Kept: {result['kept']}\n"
                    f"  Removed: {result['removed']}"
                ),
                metadata=result,
            )
        if subcommand == "compact":
            self._require_command_capability(ctx, "memory.compact", command_name="memory compact")
            keep_last = self._parse_positive_int_arg(args[1] if len(args) > 1 else None, default=20)
            result = self.compact_session_memory(keep_last=keep_last)
            return CommandResult(
                handled=True,
                output=(
                    "Memory compacted:\n"
                    f"  Session: {result['session_id']}\n"
                    f"  Kept Tail: {result['kept_tail']}\n"
                    f"  Compacted: {result['compacted_entries']}"
                ),
                metadata=result,
            )
        return CommandResult(
            handled=True,
            output="Usage: /memory <show|trim [keep_last]|compact [keep_last]>",
        )

    def _invoke_checkpoint_command(self, args: list[str], ctx: CommandContext) -> CommandResult:
        if not args:
            return CommandResult(
                handled=True,
                output="Usage: /checkpoint <list|save <name>|restore <name>|show <name>>",
            )
        subcommand = str(args[0]).strip().lower()
        if subcommand == "list":
            self._require_command_capability(ctx, "checkpoint.read", command_name="checkpoint list")
            items = self.list_checkpoints()
            lines = ["Checkpoints:"]
            if not items:
                lines.append("  (none)")
            else:
                for item in items:
                    lines.append(
                        f"  - {item['name']} | {item.get('created_at') or '-'} | "
                        f"session={item.get('session_id') or '-'} | transcript={item.get('transcript_entries', 0)}"
                    )
            return CommandResult(handled=True, output="\n".join(lines), metadata={"checkpoints": items})
        if subcommand == "save":
            self._require_command_capability(ctx, "checkpoint.write", command_name="checkpoint save")
            if len(args) < 2:
                return CommandResult(handled=True, output="Usage: /checkpoint save <name>")
            result = self.save_checkpoint(args[1])
            return CommandResult(
                handled=True,
                output=(
                    "Checkpoint saved:\n"
                    f"  Name: {result['name']}\n"
                    f"  Session: {result['session_id']}\n"
                    f"  Path: {result['path']}"
                ),
                metadata=result,
            )
        if subcommand == "restore":
            self._require_command_capability(ctx, "checkpoint.restore", command_name="checkpoint restore")
            if len(args) < 2:
                return CommandResult(handled=True, output="Usage: /checkpoint restore <name>")
            result = self.restore_checkpoint(args[1])
            return CommandResult(
                handled=True,
                output=(
                    "Checkpoint restored:\n"
                    f"  Name: {result['name']}\n"
                    f"  Session: {result['session_id']}\n"
                    f"  Restored Transcript Entries: {result['transcript_entries']}"
                ),
                metadata=result,
            )
        if subcommand == "show":
            self._require_command_capability(ctx, "checkpoint.read", command_name="checkpoint show")
            if len(args) < 2:
                return CommandResult(handled=True, output="Usage: /checkpoint show <name>")
            result = self.get_checkpoint_details(args[1])
            return CommandResult(
                handled=True,
                output=(
                    "Checkpoint:\n"
                    f"  Name: {result['name']}\n"
                    f"  Created: {result['created_at']}\n"
                    f"  Session: {result['session_id']}\n"
                    f"  Transcript Entries: {result['transcript_entries']}"
                ),
                metadata=result,
            )
        return CommandResult(
            handled=True,
            output="Usage: /checkpoint <list|save <name>|restore <name>|show <name>>",
        )

    def _parse_positive_int_arg(self, raw: Any, *, default: int) -> int:
        if raw in {None, ""}:
            return default
        value = int(raw)
        if value < 0:
            raise ValueError("Expected a non-negative integer.")
        return value

    def _require_command_capability(self, ctx: CommandContext, capability: str, *, command_name: str) -> None:
        available = set(getattr(ctx, "capabilities", set()) or set())
        if capability in available:
            return
        raise PermissionError(
            f"Command '{command_name}' requires capability '{capability}', which is not available in this context."
        )

    def _checkpoint_dir(self) -> Path:
        return checkpoint_storage_dir(self._workspace_root, self._config)

    def _checkpoint_path(self, name: str) -> Path:
        cleaned = str(name or "").strip().replace("\\", "_").replace("/", "_")
        if not cleaned:
            raise ValueError("Checkpoint name is required.")
        return self._checkpoint_dir() / f"{cleaned}.json"

    def _utc_now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _serialize_transcript_entries(self, entries: list[Any]) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for entry in entries or []:
            as_dict = getattr(entry, "as_dict", None)
            if callable(as_dict):
                serialized.append(dict(as_dict()))
            elif isinstance(entry, dict):
                serialized.append(dict(entry))
        return serialized

    def _load_active_session_record(self) -> Any:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            raise RuntimeError("Session persistence is not available.")
        self._ensure_active_session()
        session_id = getattr(self, "active_session_id", None)
        if not session_id:
            raise RuntimeError("No active session.")
        self._update_active_session_snapshot()
        return session_manager.load_session(session_id)

    def trim_session_memory(self, *, keep_last: int = 20) -> Dict[str, Any]:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            raise RuntimeError("Session persistence is not available.")
        record = self._load_active_session_record()
        transcript = list(getattr(record, "transcript", []) or [])
        kept_entries = transcript[-keep_last:] if keep_last > 0 else []
        removed = max(len(transcript) - len(kept_entries), 0)
        updated = session_manager.update_session(record.session_id, transcript=kept_entries)
        return {
            "session_id": updated.session_id,
            "kept": len(updated.transcript),
            "removed": removed,
        }

    def compact_session_memory(self, *, keep_last: int = 20) -> Dict[str, Any]:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            raise RuntimeError("Session persistence is not available.")
        record = self._load_active_session_record()
        transcript = list(getattr(record, "transcript", []) or [])
        compacted_entries = transcript[:-keep_last] if keep_last > 0 else transcript
        kept_tail = transcript[-keep_last:] if keep_last > 0 else []
        if not compacted_entries:
            return {
                "session_id": record.session_id,
                "kept_tail": len(kept_tail),
                "compacted_entries": 0,
                "summary_entry": None,
            }
        preview = " | ".join(
            str(getattr(entry, "content", "")).strip().replace("\n", " ")[:80]
            for entry in compacted_entries[:3]
            if str(getattr(entry, "content", "")).strip()
        )
        summary_entry = {
            "entry_id": uuid4().hex,
            "timestamp": self._utc_now_iso(),
            "role": "system",
            "content": (
                f"[compacted {len(compacted_entries)} earlier transcript entries]"
                + (f" {preview}" if preview else "")
            ),
            "run_id": None,
            "metadata": {"kind": "memory_compaction", "compacted_entries": len(compacted_entries)},
        }
        updated = session_manager.update_session(record.session_id, transcript=[summary_entry, *kept_tail])
        return {
            "session_id": updated.session_id,
            "kept_tail": len(kept_tail),
            "compacted_entries": len(compacted_entries),
            "summary_entry": summary_entry["content"],
        }

    def save_checkpoint(self, name: str) -> Dict[str, Any]:
        record = self._load_active_session_record()
        payload = {
            "name": str(name).strip(),
            "created_at": self._utc_now_iso(),
            "session_id": record.session_id,
            "session_title": getattr(record, "title", None),
            "state": self._session_state_payload(),
            "transcript": self._serialize_transcript_entries(list(getattr(record, "transcript", []) or [])),
        }
        path = self._checkpoint_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
        return {
            "name": payload["name"],
            "path": str(path),
            "created_at": payload["created_at"],
            "session_id": payload["session_id"],
            "transcript_entries": len(payload["transcript"]),
        }

    def _load_checkpoint_payload(self, name: str) -> Dict[str, Any]:
        path = self._checkpoint_path(name)
        if not path.exists():
            raise ValueError(f"Unknown checkpoint '{name}'.")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Checkpoint '{name}' is invalid.")
        return raw

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        checkpoint_dir = self._checkpoint_dir()
        if not checkpoint_dir.exists():
            return []
        items: list[Dict[str, Any]] = []
        for path in sorted(checkpoint_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            items.append(
                {
                    "name": str(raw.get("name") or path.stem),
                    "created_at": str(raw.get("created_at") or ""),
                    "session_id": str(raw.get("session_id") or ""),
                    "transcript_entries": len(raw.get("transcript") or []),
                    "path": str(path),
                }
            )
        items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return items

    def get_checkpoint_details(self, name: str) -> Dict[str, Any]:
        raw = self._load_checkpoint_payload(name)
        return {
            "name": str(raw.get("name") or name),
            "created_at": str(raw.get("created_at") or ""),
            "session_id": str(raw.get("session_id") or ""),
            "transcript_entries": len(raw.get("transcript") or []),
            "state": dict(raw.get("state") or {}),
        }

    def restore_checkpoint(self, name: str) -> Dict[str, Any]:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            raise RuntimeError("Session persistence is not available.")
        raw = self._load_checkpoint_payload(name)
        state = dict(raw.get("state") or {})
        active_session_id = getattr(self, "active_session_id", None)
        if not active_session_id:
            raise RuntimeError("No active session.")
        current_record = session_manager.load_session(active_session_id)
        transcript = list(raw.get("transcript") or [])
        updated = session_manager.update_session(
            current_record.session_id,
            active_agent=state.get("active_agent"),
            active_profile=state.get("active_profile"),
            enabled_skills=list(state.get("enabled_skills") or []),
            global_llm_profile=state.get("global_llm_profile"),
            session_global_skills_override=list(state.get("session_global_skills_override") or []),
            session_profile_overrides=dict(state.get("session_profile_overrides") or {}),
            session_confirmation_overrides=dict(state.get("session_confirmation_overrides") or {}),
            debugger_breakpoints=list(state.get("debugger_breakpoints") or []),
            transcript=transcript,
        )
        self._restore_saved_session(updated)
        self.active_session_id = updated.session_id
        self.active_session_title = updated.title
        self.active_session_loaded_from_history = True
        self._update_active_session_snapshot()
        return {
            "name": str(raw.get("name") or name),
            "session_id": updated.session_id,
            "transcript_entries": len(updated.transcript),
        }

    def create_markdown_asset(self, asset_kind: str, name: str) -> Dict[str, Any]:
        normalized_kind = str(asset_kind or "").strip().lower()
        normalized_name = self._normalize_asset_file_name(name)
        if normalized_kind not in {"agent", "flow", "tool"}:
            raise ValueError("Unsupported asset kind. Expected one of: agent, flow, tool.")

        resource_root = primary_resource_root(self._workspace_root)
        target_dir = resource_root.path
        target_dir.mkdir(parents=True, exist_ok=True)
        asset_path = self._workspace_markdown_asset_path(normalized_kind, normalized_name, resource_root=resource_root)
        if asset_path.exists():
            raise ValueError(f"{normalized_kind.title()} asset already exists: {asset_path}")
        asset_path.parent.mkdir(parents=True, exist_ok=True)

        companion_path: Path | None = None
        if normalized_kind == "tool":
            companion_path = target_dir / self._tool_handler_filename(normalized_name)
            if companion_path.exists():
                raise ValueError(f"Tool handler module already exists: {companion_path}")
            companion_path.write_text(
                self._tool_python_scaffold(normalized_name),
                encoding="utf-8",
            )

        asset_path.write_text(
            self._markdown_asset_scaffold(normalized_kind, normalized_name),
            encoding="utf-8",
        )
        self.reload()
        return {
            "kind": normalized_kind,
            "name": normalized_name,
            "path": asset_path,
            "companion_path": companion_path,
            "resource_root": resource_root.path,
        }

    def create_stackvm_flow(
        self,
        name: str,
        *,
        entry: str = "decide",
        agent_name: str | None = None,
    ) -> Dict[str, Any]:
        normalized_name = self._normalize_asset_file_name(name)
        normalized_entry = self._normalize_stackvm_entry_word(entry)
        self.create_markdown_asset("flow", normalized_name)
        markdown_text = self._stackvm_flow_scaffold(normalized_name, entry=normalized_entry)
        updated = self.update_markdown_asset("flow", normalized_name, markdown_text=markdown_text)

        created_agent: Dict[str, Any] | None = None
        if agent_name:
            created_agent = self.create_stackvm_agent(agent_name, flow_name=normalized_name)

        return {
            "kind": "flow",
            "name": normalized_name,
            "path": updated["path"],
            "entry": normalized_entry,
            "agent": created_agent,
        }

    def create_stackvm_script(
        self,
        name: str,
        *,
        entry: str = "main",
    ) -> Dict[str, Any]:
        normalized_name = self._normalize_stackvm_script_name(name)
        normalized_entry = self._normalize_stackvm_entry_word(entry)
        script_path = self._stackvm_script_root() / f"{normalized_name}.vm"
        if script_path.exists():
            raise ValueError(f"StackVM script already exists: {script_path}")
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(
            self._stackvm_script_scaffold(normalized_name, entry=normalized_entry),
            encoding="utf-8",
        )
        return {
            "kind": "script",
            "name": normalized_name,
            "path": script_path,
            "entry": normalized_entry,
        }

    def create_stackvm_agent(self, name: str, *, flow_name: str) -> Dict[str, Any]:
        normalized_name = self._normalize_asset_file_name(name)
        normalized_flow = self._require_known_agent_name(flow_name)
        existing_profile = self.get_agent_profile(normalized_name)
        if existing_profile is not None:
            raise ValueError(f"Agent profile '{normalized_name}' already exists.")

        resource_root = primary_resource_root(self._workspace_root)
        asset_path = self._workspace_markdown_asset_path("agent", normalized_name, resource_root=resource_root)
        if asset_path.exists():
            raise ValueError(f"Agent asset already exists: {asset_path}")
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_text = self._stackvm_agent_scaffold(normalized_name, flow_name=normalized_flow)
        asset_path.write_text(markdown_text, encoding="utf-8")
        self.reload()
        return {
            "kind": "agent",
            "name": normalized_name,
            "path": asset_path,
            "flow": normalized_flow,
        }

    def list_stackvm_scripts(self) -> List[str]:
        script_root = self._stackvm_script_root()
        if not script_root.is_dir():
            return []

        scripts: list[str] = []
        for path in sorted(script_root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".vm", ".md"}:
                continue
            scripts.append(path.relative_to(script_root).as_posix())
        return scripts

    def get_stackvm_script(self, name_or_path: str) -> Dict[str, Any]:
        script_path = self._resolve_stackvm_script_path(name_or_path)
        return {
            "name": self._stackvm_script_display_name(script_path),
            "path": script_path,
            "text": script_path.read_text(encoding="utf-8"),
        }

    def update_stackvm_script(self, name_or_path: str, *, source_text: str) -> Dict[str, Any]:
        script_path = self._resolve_stackvm_script_path(name_or_path, create_if_missing=True)
        validation_source = self._stackvm_source_from_script_text(script_path=script_path, source_text=source_text)
        compiled = self._compile_stackvm_program(
            source=validation_source,
            source_files=[str(script_path)],
            entry=None,
        )
        if not compiled["source"].strip():
            raise ValueError(f"StackVM script '{script_path}' has no executable source.")
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(source_text.rstrip() + "\n", encoding="utf-8")
        return {
            "name": self._stackvm_script_display_name(script_path),
            "path": script_path,
            "warnings": compiled["warnings"],
        }

    def inspect_stackvm_target(
        self,
        target_kind: str,
        target_name: str,
        *,
        entry: str | None = None,
    ) -> Dict[str, Any]:
        normalized_kind = str(target_kind or "").strip().lower()
        normalized_entry = self._normalize_stackvm_entry_word(entry) if entry else None

        if normalized_kind == "flow":
            flow_name, definition = self._resolve_stackvm_flow_definition(target_name)
            compiled = self._load_and_compile_stackvm_flow(definition=definition, entry=normalized_entry)
            return {
                "target_kind": "flow",
                "name": flow_name,
                "path": self._flow_markdown_path(definition),
                "flow": flow_name,
                "agent": None,
                "execution_mode": definition.execution_mode,
                "vm_entry": normalized_entry or definition.vm_entry,
                "llm_profile": definition.llm_profile,
                "tools": list(definition.tools),
                "prompt_sources": list(definition.prompt_sources),
                **compiled,
            }

        if normalized_kind == "script":
            script_path = self._resolve_stackvm_script_path(target_name)
            script_entry = normalized_entry or "main"
            source, source_files = load_stackvm_program_source(
                vm_source=None,
                vm_entry=script_entry,
                vm_module=None,
                vm_modules=[],
                vm_module_prefixes={},
                vm_file=str(script_path),
                vm_files=[],
                base_dir=script_path.parent,
                search_roots=[script_path.parent, self._stackvm_script_root(), self._workspace_root],
            )
            compiled = self._compile_stackvm_program(
                source=source,
                source_files=source_files,
                entry=script_entry,
            )
            return {
                "target_kind": "script",
                "name": self._stackvm_script_display_name(script_path),
                "path": script_path,
                "flow": None,
                "agent": None,
                "execution_mode": "vm",
                "vm_entry": script_entry,
                "llm_profile": None,
                "tools": [],
                "prompt_sources": [],
                **compiled,
            }

        if normalized_kind == "agent":
            profile = self.get_agent_profile(target_name)
            if profile is None:
                raise ValueError(f"Unknown agent profile '{target_name}'.")
            flow_name, definition = self._resolve_stackvm_flow_definition(profile.flow)
            compiled = self._load_and_compile_stackvm_flow(definition=definition, entry=normalized_entry)
            return {
                "target_kind": "agent",
                "name": profile.name,
                "path": getattr(profile, "source_path", None),
                "flow": flow_name,
                "agent": profile.name,
                "execution_mode": definition.execution_mode,
                "vm_entry": normalized_entry or definition.vm_entry,
                "llm_profile": profile.llm_profile,
                "tools": list(profile.tools) if profile.tools is not None else self.list_tools_for_agent(flow_name),
                "prompt_sources": list(profile.extra_prompts),
                "profile_source": getattr(profile, "source", None),
                "profile_path": getattr(profile, "source_path", None),
                **compiled,
            }

        raise ValueError("Unsupported StackVM target. Expected one of: flow, script, agent.")

    def run_stackvm_target(
        self,
        target_kind: str,
        target_name: str,
        *,
        request: str = "",
        entry: str | None = None,
        debug: bool = False,
        auto_confirm_tools: bool = True,
    ) -> Dict[str, Any]:
        normalized_kind = str(target_kind or "").strip().lower()
        normalized_entry = self._normalize_stackvm_entry_word(entry) if entry else None

        if normalized_kind == "flow":
            flow_name, definition = self._resolve_stackvm_flow_definition(target_name)
            profile = self._get_default_profile_for(flow_name)
            return self._run_stackvm_flow_definition(
                flow_name=flow_name,
                definition=definition,
                request=request,
                active_profile=profile,
                debug=debug,
                auto_confirm_tools=auto_confirm_tools,
                entry_override=normalized_entry,
            )

        if normalized_kind == "agent":
            profile = self.get_agent_profile(target_name)
            if profile is None:
                raise ValueError(f"Unknown agent profile '{target_name}'.")
            flow_name, definition = self._resolve_stackvm_flow_definition(profile.flow)
            return self._run_stackvm_flow_definition(
                flow_name=flow_name,
                definition=definition,
                request=request,
                active_profile=profile,
                debug=debug,
                auto_confirm_tools=auto_confirm_tools,
                entry_override=normalized_entry,
            )

        if normalized_kind == "script":
            script_path = self._resolve_stackvm_script_path(target_name)
            script_entry = normalized_entry or "main"
            source, source_files = load_stackvm_program_source(
                vm_source=None,
                vm_entry=script_entry,
                vm_module=None,
                vm_modules=[],
                vm_module_prefixes={},
                vm_file=str(script_path),
                vm_files=[],
                base_dir=script_path.parent,
                search_roots=[script_path.parent, self._stackvm_script_root(), self._workspace_root],
            )
            definition = FlowDefinition(
                name=script_path.stem,
                description=f"StackVM script '{script_path.name}'",
                execution_mode="vm",
                tools=sorted(self._catalog.tools.keys()),
                vm_entry=script_entry,
                vm_file=str(script_path),
                metadata={
                    "namespace": "__stackvm_cli__",
                    "namespace_root": str(script_path.parent),
                    "resource_root": str(self._stackvm_script_root().parent),
                    "markdown_path": str(script_path),
                },
            )
            temp_profile = AgentProfile(
                name=f"stackvm-script.{script_path.stem}",
                flow="__stackvm_cli__.script",
                description=f"Temporary profile for {script_path.name}",
                source="synthesised",
            )
            return self._run_stackvm_temp_script(
                script_path=script_path,
                source_files=source_files,
                definition=definition,
                active_profile=temp_profile,
                request=request,
                debug=debug,
                auto_confirm_tools=auto_confirm_tools,
            )

        raise ValueError("Unsupported StackVM target. Expected one of: flow, script, agent.")

    def list_markdown_assets(self, asset_kind: str) -> List[str]:
        normalized_kind = str(asset_kind or "").strip().lower()
        if normalized_kind == "agent":
            return sorted(
                profile.name
                for profile in self._agent_profile_manager.list()
                if getattr(profile, "source", None) == "workspace"
                and getattr(profile, "source_path", None) is not None
                and Path(profile.source_path).suffix.lower() == ".md"
            )

        if normalized_kind == "flow":
            assets: set[str] = set()
            for _, flow_def in self._catalog.flows.items():
                path = self._flow_markdown_path(flow_def)
                if path is None or not self._is_workspace_asset_path(path):
                    continue
                assets.add(str(flow_def.name))
            return sorted(assets)

        if normalized_kind == "tool":
            assets: set[str] = set()
            for qualified_name, tool_impl in self._catalog.tools.items():
                path = self._tool_markdown_path(tool_impl)
                if path is None or not self._is_workspace_asset_path(path):
                    continue
                _, _, local_name = qualified_name.partition(".")
                assets.add(local_name or qualified_name)
            return sorted(assets)

        raise ValueError("Unsupported asset kind. Expected one of: agent, flow, tool.")

    def clone_markdown_asset(self, asset_kind: str, source_name: str, new_name: str) -> Dict[str, Any]:
        normalized_kind = str(asset_kind or "").strip().lower()
        normalized_name = self._normalize_asset_file_name(new_name)
        source_asset = self.get_markdown_asset(normalized_kind, source_name)
        source_path = Path(source_asset["path"]).resolve()
        if normalized_kind == "agent":
            target_path = self._workspace_markdown_asset_path(normalized_kind, normalized_name)
        else:
            target_path = source_path.with_name(self._markdown_asset_filename(normalized_kind, normalized_name))
        if target_path.exists():
            raise ValueError(f"{normalized_kind.title()} asset already exists: {target_path}")

        markdown_text, companion_text, companion_path = self._clone_markdown_asset_contents(
            asset_kind=normalized_kind,
            source_path=source_path,
            source_text=str(source_asset["text"]),
            new_name=normalized_name,
        )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        if companion_path is not None and companion_text is not None:
            companion_path.parent.mkdir(parents=True, exist_ok=True)
            companion_path.write_text(companion_text, encoding="utf-8")
        try:
            self._validate_markdown_asset_text(
                normalized_kind,
                markdown_text=markdown_text,
                target_name=normalized_name,
                target_path=target_path,
            )
        except Exception:
            if companion_path is not None and companion_path.exists():
                companion_path.unlink()
            raise
        target_path.write_text(markdown_text, encoding="utf-8")

        self.reload()
        return {
            "kind": normalized_kind,
            "name": normalized_name,
            "path": target_path,
            "companion_path": companion_path,
        }

    def update_markdown_asset(self, asset_kind: str, name: str, *, markdown_text: str) -> Dict[str, Any]:
        asset = self.get_markdown_asset(asset_kind, name)
        normalized_kind = str(asset_kind or "").strip().lower()
        path = Path(asset["path"]).resolve()
        validated_name = self._validate_markdown_asset_text(
            normalized_kind,
            markdown_text=markdown_text,
            target_name=str(name or "").strip(),
            target_path=path,
        )
        path.write_text(markdown_text.strip() + "\n", encoding="utf-8")
        self.reload()
        return {
            "kind": normalized_kind,
            "name": validated_name,
            "path": path,
            "companion_path": asset.get("companion_path"),
        }

    def delete_markdown_asset(self, asset_kind: str, name: str) -> Dict[str, Any]:
        asset = self.get_markdown_asset(asset_kind, name)
        normalized_kind = str(asset_kind or "").strip().lower()
        target_path = Path(asset["path"]).resolve()
        companion_path = asset.get("companion_path")

        if normalized_kind == "agent":
            deleted_path = self.delete_agent_profile(str(name or "").strip())
            return {
                "kind": normalized_kind,
                "name": str(name or "").strip(),
                "path": deleted_path,
                "companion_path": companion_path,
                "companion_deleted": False,
            }

        if not target_path.exists():
            raise ValueError(f"Markdown asset file does not exist: {target_path}")
        target_path.unlink()
        self.reload()
        return {
            "kind": normalized_kind,
            "name": str(name or "").strip(),
            "path": target_path,
            "companion_path": companion_path,
            "companion_deleted": False,
        }

    def get_markdown_asset(self, asset_kind: str, name: str) -> Dict[str, Any]:
        normalized_kind = str(asset_kind or "").strip().lower()
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise ValueError("Asset name must not be empty.")

        if normalized_kind == "agent":
            profile = self.get_agent_profile(normalized_name)
            if profile is None:
                raise ValueError(f"Unknown agent profile '{normalized_name}'.")
            source_path = getattr(profile, "source_path", None)
            if getattr(profile, "source", None) != "workspace" or source_path is None:
                raise ValueError(f"Agent '{normalized_name}' is not a workspace markdown asset.")
            path = Path(source_path)
            if path.suffix.lower() != ".md":
                raise ValueError(f"Agent '{normalized_name}' is not stored as Markdown.")
            return {
                "kind": normalized_kind,
                "name": profile.name,
                "path": path,
                "companion_path": None,
                "text": path.read_text(encoding="utf-8"),
            }

        if normalized_kind == "flow":
            flow_def, path = self._resolve_workspace_markdown_flow(normalized_name)
            return {
                "kind": normalized_kind,
                "name": flow_def.name,
                "path": path,
                "companion_path": None,
                "text": path.read_text(encoding="utf-8"),
            }

        if normalized_kind == "tool":
            _, local_name, tool_impl, path = self._resolve_workspace_markdown_tool(normalized_name)
            companion_path = self._tool_handler_path_from_markdown(path, tool_impl)
            return {
                "kind": normalized_kind,
                "name": local_name,
                "path": path,
                "companion_path": companion_path,
                "text": path.read_text(encoding="utf-8"),
            }

        raise ValueError("Unsupported asset kind. Expected one of: agent, flow, tool.")

    def reload(self) -> None:
        self._catalog.load()
        # T014: reload APM after the catalog reloads.
        self._agent_profile_manager.reload(dict(self._catalog.agents))
        self._skill_manager.set_registries(
            tool_registry=self._catalog.tools,
            prompt_registry=self._catalog.prompts,
        )
        self._skill_manager.load()
        self._workspace_llm_profile_manager.load()
        self._validate_loaded_reference_surfaces()
        # Re-apply active profile by name if it still exists; else fall back to
        # the current agent's default profile.
        if self.active_agent_profile is not None:
            still_exists = self._agent_profile_manager.get(self.active_agent_profile.name)
            if still_exists is not None:
                self.active_agent_profile = self._apply_session_profile_overrides(still_exists)
            elif self.current_agent:
                self._activate_default_profile_for(self.current_agent)
            else:
                self.active_agent_profile = None
        self._llm_router = LlmRouter(config=self._config, resource_root_llm_profiles=self._merged_llm_profiles())
        self.config_llm_overrides = self._build_llm_overrides_config()
        self._tool_confirmation_config = self._build_tool_confirmation_config()
        self.enabled_skills = [name for name in self.enabled_skills if self._skill_manager.get(name) is not None]
        self._refresh_runtime_components()
        self._agent_tools_cache = {}
        self._validate_current_selections()
        self._ensure_active_session()

    def _validate_current_selections(self) -> None:
        if self.current_agent and self.current_agent not in self._catalog.agents:
            self.current_agent = None

        invalid_agent_overrides = [
            agent_name
            for agent_name in self.agent_llm_overrides.keys()
            if agent_name not in self._catalog.agents
        ]
        for agent_name in invalid_agent_overrides:
            self.agent_llm_overrides.pop(agent_name, None)

        invalid_handoff_overrides = []
        for handoff_key in self.handoff_llm_overrides.keys():
            source, _, target = handoff_key.partition("->")
            if source not in self._catalog.agents or target not in self._catalog.agents:
                invalid_handoff_overrides.append(handoff_key)
        for handoff_key in invalid_handoff_overrides:
            self.handoff_llm_overrides.pop(handoff_key, None)

        self.enabled_skills = [
            skill_name
            for skill_name in self.enabled_skills
            if self._skill_manager.get(skill_name) is not None
        ]

    def _validate_loaded_reference_surfaces(self) -> None:
        self._validate_loaded_agent_profiles()
        self._validate_loaded_skills()

    def _validate_loaded_agent_profiles(self) -> None:
        profile_manager = getattr(self, "_agent_profile_manager", None)
        if profile_manager is None:
            return
        catalog = self._runtime_catalog()
        agents_registry = getattr(catalog, "agents", {})

        for raw_profile in list(profile_manager.list()):
            profile = profile_manager.resolve(raw_profile.name) if hasattr(profile_manager, "resolve") else raw_profile
            if profile is None:
                logger.warning(
                    "Agent profile '%s' could not be resolved after inheritance. Removing it from the loaded registry.",
                    raw_profile.name,
                )
                self._drop_loaded_profile(raw_profile.name)
                continue
            normalized_agent_name = self._normalize_agent_name(profile.flow)
            if not normalized_agent_name or normalized_agent_name not in agents_registry:
                logger.warning(
                    "Agent profile '%s' targets unknown agent '%s'. Removing it from the loaded registry.",
                    profile.name,
                    profile.flow,
                )
                self._drop_loaded_profile(profile.name)
                continue

            context_namespace = self._context_namespace_for_agent(normalized_agent_name)
            profile.flow = normalized_agent_name
            if profile.tools is not None:
                profile.tools = self._qualify_existing_tool_refs(
                    profile.tools,
                    owner_name=profile.name,
                    field_name="tools",
                    context_agent=normalized_agent_name,
                )
            if profile.hooks is not None:
                profile.hooks = self._qualify_existing_hook_refs(
                    profile.hooks,
                    owner_name=profile.name,
                    field_name="hooks",
                    context_namespace=context_namespace,
                )
            profile.extra_prompts = self._filter_existing_prompt_refs(
                profile.extra_prompts,
                owner_name=profile.name,
                field_name="extra_prompts",
                context_namespace=context_namespace,
                allow_context_deferred=False,
            )
            self._store_loaded_profile(profile)

    def _validate_loaded_skills(self) -> None:
        skill_manager = getattr(self, "_skill_manager", None)
        if skill_manager is None:
            return

        for skill in list(skill_manager.list()):
            updated_skill = dataclasses.replace(
                skill,
                tool_refs=self._qualify_existing_tool_refs(
                    skill.tool_refs,
                    owner_name=skill.name,
                    field_name="tools",
                    context_agent=None,
                    allow_context_deferred=True,
                ),
                extra_prompts=self._filter_existing_prompt_refs(
                    skill.extra_prompts,
                    owner_name=skill.name,
                    field_name="extra_prompts",
                    context_namespace=None,
                    allow_context_deferred=True,
                ),
            )
            self._store_loaded_skill(updated_skill)

    def _qualify_existing_tool_refs(
        self,
        refs: List[str],
        *,
        owner_name: str,
        field_name: str,
        context_agent: str | None,
        allow_context_deferred: bool = False,
    ) -> List[str]:
        qualified: List[str] = []
        for ref in refs:
            candidate = str(ref or "").strip()
            if not candidate:
                continue
            if candidate == "*":
                return ["*"]
            if candidate.startswith("skill."):
                if candidate not in qualified:
                    qualified.append(candidate)
                continue

            try:
                normalized_candidate = parse_reference(candidate, allowed_kinds={"tool"})
            except ValueError as exc:
                logger.warning(
                    "Resource '%s' has invalid %s ref '%s': %s. Skipping it.",
                    owner_name,
                    field_name,
                    candidate,
                    exc,
                )
                continue

            if allow_context_deferred and context_agent is None and not normalized_candidate.is_qualified:
                if candidate not in qualified:
                    qualified.append(candidate)
                continue

            try:
                resolved = self._qualify_tool_reference(candidate, context_agent=context_agent)
            except ValueError as exc:
                logger.warning(
                    "Resource '%s' has invalid %s ref '%s': %s. Skipping it.",
                    owner_name,
                    field_name,
                    candidate,
                    exc,
                )
                continue
            if resolved and resolved not in qualified:
                qualified.append(resolved)
        return qualified

    def _qualify_existing_hook_refs(
        self,
        refs: List[str],
        *,
        owner_name: str,
        field_name: str,
        context_namespace: str | None,
    ) -> List[str]:
        qualified: List[str] = []
        for candidate in refs:
            try:
                normalized = parse_reference(candidate, allowed_kinds={"hook"})
            except ValueError as exc:
                logger.warning(
                    "Dropping invalid %s reference '%s' from '%s': %s",
                    field_name,
                    candidate,
                    owner_name,
                    exc,
                )
                continue

            target = normalized.as_registry_key()
            try:
                qualified_name = self._catalog.hooks.qualify(target, context_namespace=context_namespace)
            except RegistryError:
                logger.warning(
                    "Dropping unknown %s reference '%s' from '%s'.",
                    field_name,
                    candidate,
                    owner_name,
                )
                continue
            if qualified_name not in qualified:
                qualified.append(qualified_name)
        return qualified

    def _filter_existing_prompt_refs(
        self,
        refs: List[str],
        *,
        owner_name: str,
        field_name: str,
        context_namespace: str | None,
        allow_context_deferred: bool,
    ) -> List[str]:
        filtered: List[str] = []
        catalog = self._runtime_catalog()
        prompt_registry = getattr(catalog, "prompts", None)
        for ref in refs:
            candidate = str(ref or "").strip()
            if not candidate:
                continue
            if not is_prompt_reference(candidate):
                filtered.append(candidate)
                continue

            try:
                normalized_candidate = parse_prompt_reference(candidate)
            except ValueError as exc:
                logger.warning(
                    "Resource '%s' has invalid %s ref '%s': %s. Skipping it.",
                    owner_name,
                    field_name,
                    candidate,
                    exc,
                )
                continue
            if allow_context_deferred and context_namespace is None and not normalized_candidate.is_qualified:
                filtered.append(candidate)
                continue

            try:
                _prompt_text, prompt_sources = resolve_prompt_reference(
                    candidate,
                    prompt_registry=prompt_registry,
                    context_namespace=context_namespace,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Resource '%s' has invalid %s ref '%s': %s. Skipping it.",
                    owner_name,
                    field_name,
                    candidate,
                    exc,
                )
                continue

            canonical_ref = next(
                (source for source in prompt_sources if isinstance(source, str) and source.startswith("prompt:")),
                candidate,
            )
            if canonical_ref not in filtered:
                filtered.append(canonical_ref)
        return filtered

    def _context_namespace_for_agent(self, agent_name: str | None) -> str | None:
        if not agent_name:
            return None
        catalog = self._runtime_catalog()
        agents_registry = getattr(catalog, "agents", None)
        if agents_registry is None:
            return None
        agent_definition = agents_registry.get(agent_name)
        if agent_definition is None:
            return None
        return namespace_name_from_metadata(
            getattr(agent_definition, "metadata", {}) or {},
            fallback_qualified_name=agent_name,
        )

    def _store_loaded_profile(self, profile: AgentProfile) -> None:
        manager = getattr(self, "_agent_profile_manager", None)
        mapping = self._manager_store(manager, "_agents", "_profiles")
        if mapping is not None:
            mapping[profile.name] = profile

    def _drop_loaded_profile(self, profile_name: str) -> None:
        manager = getattr(self, "_agent_profile_manager", None)
        mapping = self._manager_store(manager, "_agents", "_profiles")
        if mapping is not None:
            mapping.pop(profile_name, None)

    def _store_loaded_skill(self, skill: SkillDefinition) -> None:
        manager = getattr(self, "_skill_manager", None)
        mapping = self._manager_store(manager, "_skills")
        if mapping is not None:
            mapping[skill.name] = skill

    def _manager_store(self, manager: Any, *attr_names: str) -> Dict[str, Any] | None:
        for attr_name in attr_names:
            mapping = getattr(manager, attr_name, None)
            if isinstance(mapping, dict):
                return mapping
        return None

    def list_agents(self) -> List[str]:
        """Return registered agent/flow names."""
        return sorted(self._catalog.agents.keys())

    def list_flows(self) -> List[str]:
        return self.list_agents()

    def list_prompts(self) -> List[str]:
        return self._catalog.prompts.list_all()

    def list_llm_profiles(self) -> List[str]:
        return self._llm_router.list_profile_names()

    def get_llm_profile(self, name: Optional[str] = None) -> Any:
        target_name = str(name or self._selected_llm_profile() or "").strip()
        if not target_name:
            return None

        workspace_entry = self._workspace_llm_profile_manager.get(target_name)
        if workspace_entry is not None:
            return {
                "name": target_name,
                "source": "workspace",
                "source_path": workspace_entry.get("source_path"),
                "config": copy.deepcopy(workspace_entry.get("config", {})),
            }

        resource_root_profile = self._catalog.llm_profiles.get(target_name)
        if isinstance(resource_root_profile, dict):
            return {
                "name": target_name,
                "source": "resource_root",
                "source_path": None,
                "config": copy.deepcopy(resource_root_profile),
            }

        configured_profiles = self._llm_config.get("profiles", {})
        if isinstance(configured_profiles, dict):
            configured_profile = configured_profiles.get(target_name)
            if isinstance(configured_profile, dict):
                return {
                    "name": target_name,
                    "source": "config",
                    "source_path": self._workspace_root / "pocketcode.yml",
                    "config": copy.deepcopy(configured_profile),
                }

        resolved = self._llm_router.resolve_profile_config(target_name)
        return {
            "name": target_name,
            "source": "runtime",
            "source_path": None,
            "config": resolved,
        }

    def get_current_agent(self):
        """Return the current agent/flow selection."""
        return self.current_agent

    def get_current_flow(self):
        return self.get_current_agent()

    def _runtime_catalog(self) -> Any:
        return getattr(self, "_catalog", None)

    def _normalize_textual_control_presentation(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in {"modal", "popup", "popups"}:
            return "modal"
        return "inline"

    def get_system_settings(self) -> Dict[str, Any]:
        textual_config = self._runtime_config.get("textual", {})
        if not isinstance(textual_config, dict):
            textual_config = {}
        control_presentation = self._normalize_textual_control_presentation(
            textual_config.get("control_presentation")
        )
        return {
            "theme_name": str(textual_config.get("theme_name") or "ocean"),
            "workspace_view": str(textual_config.get("workspace_view") or "balanced"),
            "default_agent": self._normalize_agent_name(self._runtime_config.get("default_agent")),
            "default_llm_profile": self._llm_config.get("default_profile"),
            "control_presentation": control_presentation,
        }

    def get_textual_selection_settings(self) -> Dict[str, Any]:
        textual_config = self._runtime_config.get("textual", {})
        if not isinstance(textual_config, dict):
            textual_config = {}
        last_used = textual_config.get("last_used", {})
        if not isinstance(last_used, dict):
            last_used = {}
        agent_profiles = last_used.get("agent_profiles", {})
        if not isinstance(agent_profiles, dict):
            agent_profiles = {}
        default_skills = textual_config.get("default_skills", [])
        last_used_skills = last_used.get("skills", [])
        presets = textual_config.get("selection_presets", {})
        return {
            "default_skills": list(default_skills) if isinstance(default_skills, list) else [],
            "last_used_skills": list(last_used_skills) if isinstance(last_used_skills, list) else [],
            "agent_profiles": copy.deepcopy(agent_profiles),
            "active_profile": last_used.get("active_profile"),
            "global_llm_profile": last_used.get("global_llm_profile"),
            "session_confirmation_default": last_used.get("session_confirmation_default"),
            "auto_confirm_tools": bool(last_used.get("auto_confirm_tools", self.auto_confirm_tools)),
            "selection_presets": sorted(presets) if isinstance(presets, dict) else [],
        }

    def save_system_settings(
        self,
        *,
        theme_name: str,
        workspace_view: str,
        default_agent: Optional[str],
        default_llm_profile: Optional[str],
        control_presentation: str = "inline",
    ) -> Path:
        normalized_default_agent = self._normalize_agent_name(default_agent)
        catalog = self._runtime_catalog()
        agents_registry = getattr(catalog, "agents", {})
        if normalized_default_agent:
            if normalized_default_agent not in agents_registry:
                raise KeyError(f"Unknown agent '{default_agent}'.")
        if default_llm_profile:
            self._llm_router.resolve_profile_config(default_llm_profile)
        normalized_control_presentation = self._normalize_textual_control_presentation(control_presentation)

        runtime_section = self._config.setdefault("runtime", {})
        if not isinstance(runtime_section, dict):
            runtime_section = {}
            self._config["runtime"] = runtime_section
        llm_section = self._config.setdefault("llm", {})
        if not isinstance(llm_section, dict):
            llm_section = {}
            self._config["llm"] = llm_section

        if normalized_default_agent:
            runtime_section["default_agent"] = str(normalized_default_agent)
        else:
            runtime_section.pop("default_agent", None)

        textual_section = runtime_section.get("textual", {})
        if not isinstance(textual_section, dict):
            textual_section = {}
        textual_section["theme_name"] = str(theme_name)
        textual_section["workspace_view"] = str(workspace_view)
        textual_section["control_presentation"] = normalized_control_presentation
        runtime_section["textual"] = textual_section

        if default_llm_profile:
            llm_section["default_profile"] = str(default_llm_profile)
        else:
            llm_section.pop("default_profile", None)

        self._runtime_config = runtime_section
        self._llm_config = llm_section
        config_path = self._write_workspace_config()
        self._reload_llm_runtime()
        return config_path

    def get_textual_entry_history(self) -> List[str]:
        return load_entry_history(self._workspace_root, self._config)

    def set_last_used_entry_history(self, entries: List[str]) -> Path:
        normalized_entries = normalize_entry_history(entries)
        return save_entry_history(self._workspace_root, normalized_entries, self._config)

    @property
    def active_agent(self):
        return self.active_agent_profile

    @active_agent.setter
    def active_agent(self, value):
        self.active_agent_profile = value

    def set_agent(self, agent_name: Optional[str]) -> None:
        """Select the current agent/flow."""
        normalized_agent_name = self._normalize_agent_name(agent_name)
        if not normalized_agent_name:
            self.current_agent = None
            self.active_agent_profile = None
            self.enabled_skills = self._configured_enabled_skills()
            self._maybe_refresh_runtime_components()
            return
        if normalized_agent_name not in self._catalog.agents:
            raise KeyError(f"Unknown agent '{agent_name}'.")
        self.current_agent = normalized_agent_name
        # T012: auto-activate the agent's default profile.
        self._activate_default_profile_for(normalized_agent_name)

    def set_flow(self, flow_name: Optional[str]) -> None:
        self.set_agent(flow_name)

    def set_active_agent_profile(self, name: Optional[str]) -> None:
        """Activate a named agent profile, or clear the active profile if name is None."""
        if name is None:
            self.active_agent_profile = None
            return
        profile = self._resolved_agent_profile(name)
        if profile is None:
            available = [p.name for p in self._agent_profile_manager.list()]
            raise ValueError(
                f"Unknown agent profile '{name}'. "
                f"Available: {available}"
            )
        normalized_profile_agent = self._normalize_agent_name(profile.flow)
        if not normalized_profile_agent or normalized_profile_agent not in self._catalog.agents:
            raise ValueError(
                f"Agent profile '{name}' targets unknown agent '{profile.flow}'."
        )
        self.current_agent = normalized_profile_agent
        self.active_agent_profile = self._apply_session_profile_overrides(profile)
        self.enabled_skills = self._configured_enabled_skills(self.active_agent_profile.name)
        self._maybe_refresh_runtime_components()

    def set_active_agent(self, name: Optional[str]) -> None:
        self.set_active_agent_profile(name)

    def _normalize_agent_name(self, agent_name: Any) -> Optional[str]:
        cleaned = str(agent_name or "").strip()
        if not cleaned:
            return None

        canonical_candidate = normalize_registry_reference(
            cleaned,
            allowed_kinds={"agent", "flow"},
        )

        catalog = getattr(self, "_catalog", None)
        agents_registry = getattr(catalog, "agents", None)
        if agents_registry is None:
            return canonical_candidate

        qualify = getattr(agents_registry, "qualify", None)
        if callable(qualify):
            try:
                return str(qualify(cleaned))
            except Exception:  # noqa: BLE001
                pass

        if cleaned in agents_registry:
            return cleaned

        if canonical_candidate in agents_registry:
            return canonical_candidate

        return canonical_candidate

    def _require_known_agent_name(self, agent_name: str, *, label: str = "agent") -> str:
        normalized_agent_name = self._normalize_agent_name(agent_name)
        if not normalized_agent_name or normalized_agent_name not in self._catalog.agents:
            raise KeyError(f"Unknown {label} '{agent_name}'.")
        return normalized_agent_name

    def list_skills(self) -> List[str]:
        return [skill.name for skill in self._skill_manager.list()]

    def get_skill(self, name: str) -> Any:
        return self._skill_manager.get(name)

    def get_active_skills(self) -> List[Any]:
        return [
            skill
            for skill_name in self.enabled_skills
            if (skill := self._skill_manager.get(skill_name)) is not None
        ]

    def enable_skill(self, name: str) -> None:
        skill = self._skill_manager.get(name)
        if skill is None:
            raise ValueError(f"Unknown skill '{name}'. Available: {self.list_skills()}")
        if name not in self.enabled_skills:
            self.enabled_skills.append(name)
            self._refresh_runtime_components()

    def disable_skill(self, name: str) -> None:
        if name not in self.enabled_skills:
            return
        self.enabled_skills = [skill_name for skill_name in self.enabled_skills if skill_name != name]
        self._refresh_runtime_components()

    def set_last_used_skills(self, skill_names: List[str]) -> None:
        normalized = self._normalize_skill_names(skill_names, strict=True)
        self.session_global_skills_override = list(normalized)
        self.enabled_skills = list(normalized)
        self._refresh_runtime_components()
        self._update_active_session_snapshot()

    def reset_last_used_skills(self) -> None:
        self.session_global_skills_override = None
        self.enabled_skills = self._configured_enabled_skills()
        self._refresh_runtime_components()
        self._update_active_session_snapshot()

    def set_last_used_profile_skills(self, profile_name: str, skill_names: List[str]) -> None:
        profile = self._base_agent_profile(profile_name)
        if profile is None and (self.active_agent_profile is None or self.active_agent_profile.name != profile_name):
            raise ValueError(f"Unknown agent profile '{profile_name}'.")
        normalized = self._normalize_skill_names(skill_names, strict=True)
        base_skills = self._base_skill_selection_for_profile(profile_name)
        if normalized == base_skills:
            self.reset_last_used_profile_skills(profile_name)
            return
        profile_state = self._session_profile_state(profile_name, create=True)
        profile_state["skills"] = normalized
        if self.active_agent_profile is not None and self.active_agent_profile.name == profile_name:
            self.enabled_skills = list(normalized)
            self._maybe_refresh_runtime_components()
        self._update_active_session_snapshot()

    def reset_last_used_profile_skills(self, profile_name: str) -> None:
        profile_state = self._session_profile_state(profile_name, create=True)
        profile_state.pop("skills", None)
        self._cleanup_session_profile_state(profile_name)
        if self.active_agent_profile is not None and self.active_agent_profile.name == profile_name:
            self.enabled_skills = self._configured_enabled_skills(profile_name)
            self._maybe_refresh_runtime_components()
        self._update_active_session_snapshot()

    def save_default_skills(self, skill_names: List[str]) -> Path:
        normalized = self._normalize_skill_names(skill_names, strict=True)
        textual = self._textual_config(create=True)
        textual["default_skills"] = normalized
        return self._write_workspace_config()

    def set_last_used_active_profile(self, profile_name: Optional[str]) -> Path:
        last_used = self._textual_last_used_config(create=True)
        cleaned = str(profile_name).strip() if profile_name else ""
        if cleaned:
            self.set_active_agent_profile(cleaned)
            last_used["active_profile"] = cleaned
        else:
            last_used.pop("active_profile", None)
        self._cleanup_textual_last_used_config()
        return self._write_workspace_config()

    def set_last_used_global_llm_profile(self, profile_name: Optional[str]) -> Path:
        last_used = self._textual_last_used_config(create=True)
        cleaned = str(profile_name).strip() if profile_name else ""
        if cleaned:
            self.set_global_llm_override(cleaned)
            last_used["global_llm_profile"] = cleaned
        else:
            self.set_global_llm_override(None)
            last_used.pop("global_llm_profile", None)
        self._cleanup_textual_last_used_config()
        return self._write_workspace_config()

    def set_last_used_session_confirmation_default(self, policy: Optional[str]) -> Path:
        last_used = self._textual_last_used_config(create=True)
        normalized = self._normalize_confirmation_policy(policy)
        self.set_session_confirmation_default(normalized)
        if normalized is None:
            last_used.pop("session_confirmation_default", None)
        else:
            last_used["session_confirmation_default"] = normalized
        self._cleanup_textual_last_used_config()
        return self._write_workspace_config()

    def set_last_used_auto_confirm_tools(self, enabled: bool) -> Path:
        last_used = self._textual_last_used_config(create=True)
        self.auto_confirm_tools = bool(enabled)
        if self.auto_confirm_tools == bool(self._runtime_config.get("auto_confirm_tools", False)):
            last_used.pop("auto_confirm_tools", None)
        else:
            last_used["auto_confirm_tools"] = self.auto_confirm_tools
        self._cleanup_textual_last_used_config()
        return self._write_workspace_config()

    def list_textual_selection_presets(self) -> List[str]:
        presets = self._textual_selection_presets_config(create=False)
        return sorted(str(name) for name in presets)

    def get_textual_selection_preset(self, name: str) -> Dict[str, Any] | None:
        presets = self._textual_selection_presets_config(create=False)
        raw = presets.get(name)
        if not isinstance(raw, dict):
            return None
        return self._normalize_textual_selection_snapshot(raw)

    def save_textual_selection_preset(self, name: str) -> Path:
        cleaned = str(name).strip()
        if not cleaned:
            raise ValueError("Selection preset name cannot be empty.")
        presets = self._textual_selection_presets_config(create=True)
        presets[cleaned] = self._capture_textual_selection_snapshot()
        return self._write_workspace_config()

    def apply_textual_selection_preset(self, name: str) -> Path:
        preset = self.get_textual_selection_preset(name)
        if preset is None:
            raise ValueError(f"Unknown selection preset '{name}'.")
        self._replace_last_used_selection_snapshot(preset)
        self.active_agent_profile = None
        self.global_llm_override = None
        self.session_profile_overrides = self._normalize_session_profile_overrides(preset.get("agent_profiles", {}))
        self.session_global_skills_override = (
            self._normalize_skill_names(list(preset.get("skills", [])), strict=False)
            if isinstance(preset.get("skills"), list)
            else None
        )
        self.clear_session_confirmation_overrides()
        self.auto_confirm_tools = bool(self._runtime_config.get("auto_confirm_tools", False))
        self._restore_textual_selection_state()
        if self.active_agent_profile is not None and isinstance(preset.get("skills"), list):
            active_profile_state = self._session_profile_state(self.active_agent_profile.name, create=True)
            active_profile_state.setdefault(
                "skills",
                self._normalize_skill_names(list(preset.get("skills", [])), strict=False),
            )
            self.enabled_skills = self._configured_enabled_skills(self.active_agent_profile.name)
        return self._write_workspace_config()

    def delete_textual_selection_preset(self, name: str) -> Path:
        presets = self._textual_selection_presets_config(create=True)
        cleaned = str(name).strip()
        if cleaned not in presets:
            raise ValueError(f"Unknown selection preset '{cleaned}'.")
        presets.pop(cleaned, None)
        if not presets:
            textual = self._textual_config(create=True)
            textual.pop("selection_presets", None)
        return self._write_workspace_config()

    def list_agent_profiles(self, agent_name: Optional[str] = None) -> List[str]:
        """Return known agent profile names, optionally filtered by target agent."""
        profiles = self._agent_profile_manager.list()
        if agent_name:
            normalized_agent_name = self._normalize_agent_name(agent_name)
            profiles = [
                profile
                for profile in profiles
                if self._normalize_agent_name(profile.flow) == normalized_agent_name
            ]
        return sorted({p.name for p in profiles})

    def list_available_agents(self, flow_name: Optional[str] = None) -> List[str]:
        return self.list_agent_profiles(flow_name)

    def get_agent_profile(self, name: Optional[str] = None, *, effective: bool = True) -> Any:
        """Return a named agent profile, or the active one when *name* is None."""
        if name is None:
            if effective:
                return self.active_agent_profile
            if self.active_agent_profile is None:
                return None
            return self._base_agent_profile(self.active_agent_profile.name) or self.active_agent_profile
        profile = self._resolved_agent_profile(name) if effective else self._base_agent_profile(name)
        if profile is None and self.active_agent_profile is not None and self.active_agent_profile.name == name:
            profile = self.active_agent_profile
        if not effective or profile is None:
            return profile
        return self._apply_session_profile_overrides(profile)

    def get_agent(self, name: Optional[str] = None) -> Any:
        return self.get_agent_profile(name)

    def clone_agent_profile(self, src_name: str, new_name: str) -> Any:
        """Clone an agent profile and return the new workspace-backed profile."""
        return self._agent_profile_manager.clone(src_name, new_name)

    def clone_agent(self, src_name: str, new_name: str) -> Any:
        return self.clone_agent_profile(src_name, new_name)

    def clone_llm_profile(self, src_name: str, new_name: str) -> Any:
        profile = self.get_llm_profile(src_name)
        if profile is None:
            raise ValueError(f"Unknown LLM profile '{src_name}'.")
        cloned = self._workspace_llm_profile_manager.clone(
            src_name,
            new_name,
            profile.get("config", {}),
        )
        self._reload_llm_runtime()
        return {
            "name": new_name,
            "source": "workspace",
            "source_path": cloned.get("source_path"),
            "config": copy.deepcopy(cloned.get("config", {})),
        }

    def _normalize_asset_file_name(self, name: str) -> str:
        normalized = str(name or "").strip()
        if not normalized:
            raise ValueError("Asset name must not be empty.")
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
        if any(character not in allowed for character in normalized):
            raise ValueError(
                "Asset name may contain only letters, numbers, dot, underscore, and hyphen."
            )
        if normalized.startswith(".") or ".." in normalized:
            raise ValueError("Asset name must not start with '.' or contain '..'.")
        return normalized

    def _normalize_stackvm_script_name(self, name: str) -> str:
        normalized = str(name or "").strip().replace("\\", "/")
        if not normalized:
            raise ValueError("StackVM script name must not be empty.")
        if normalized.startswith(".") or ".." in normalized:
            raise ValueError("StackVM script name must not start with '.' or contain '..'.")
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-/")
        if any(character not in allowed for character in normalized):
            raise ValueError(
                "StackVM script names may contain only letters, numbers, slash, dot, underscore, and hyphen."
            )
        return normalized.lstrip("/")

    def _normalize_stackvm_entry_word(self, entry: str | None) -> str:
        normalized = str(entry or "").strip()
        if not normalized:
            raise ValueError("StackVM entry word must not be empty.")
        if any(char.isspace() for char in normalized):
            raise ValueError("StackVM entry word must not contain whitespace.")
        return normalized

    def _stackvm_script_root(self) -> Path:
        return primary_resource_root(self._workspace_root).path / "vm"

    def _stackvm_flow_scaffold(self, name: str, *, entry: str) -> str:
        front_matter = {
            "name": name,
            "description": f"Workspace StackVM flow '{name}'.",
            "execution_mode": "vm",
            "vm_entry": entry,
        }
        front_matter_text = yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=False).strip()
        return (
            f"---\n{front_matter_text}\n---\n\n"
            "```vm\n"
            f"[ \"StackVM flow {name} ready.\" answer ] \"{entry}\" define\n"
            "```\n"
        )

    def _stackvm_script_scaffold(self, name: str, *, entry: str) -> str:
        return (
            f"! StackVM script scaffold for {name}\n"
            f"[ request \"Request: \" swap concat answer ] \"{entry}\" define\n"
        )

    def _stackvm_agent_scaffold(self, name: str, *, flow_name: str) -> str:
        front_matter = {
            "name": name,
            "flow": flow_name,
            "description": f"Workspace agent '{name}' for StackVM flow '{flow_name}'.",
        }
        front_matter_text = yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=False).strip()
        return (
            f"---\n{front_matter_text}\n---\n"
            "Describe the role, boundaries, and priorities for this StackVM-backed agent here.\n"
        )

    def _markdown_asset_scaffold(self, asset_kind: str, name: str) -> str:
        if asset_kind == "agent":
            front_matter = {
                "name": name,
                "flow": "core.react",
                "description": f"Workspace agent '{name}'.",
            }
            front_matter_text = yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=False).strip()
            return (
                f"---\n{front_matter_text}\n---\n"
                "Describe the role, boundaries, and priorities for this agent here.\n"
            )

        if asset_kind == "flow":
            front_matter = {
                "name": name,
                "description": f"Workspace markdown flow '{name}'.",
                "execution_mode": "vm",
                "vm_entry": "main",
            }
            front_matter_text = yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=False).strip()
            return (
                f"---\n{front_matter_text}\n---\n\n"
                "```vm\n"
                f"[ \"StackVM flow {name} ready.\" answer ] \"main\" define\n"
                "```\n"
            )

        if asset_kind == "tool":
            class_name = self._tool_scaffold_class_name(name)
            front_matter = {
                "name": name,
                "description": f"Workspace markdown tool '{name}'.",
                "handler": f"./{self._tool_handler_filename(name)}:{class_name}",
            }
            front_matter_text = yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=False).strip()
            return (
                f"---\n{front_matter_text}\n---\n\n"
                "Describe what this tool should do and when the agent should call it.\n\n"
                "```yaml schema\n"
                "type: object\n"
                "properties:\n"
                "  text:\n"
                "    type: string\n"
                "    description: Input text for the scaffolded tool.\n"
                "required:\n"
                "  - text\n"
                "```\n"
            )

        raise ValueError(f"Unsupported asset kind: {asset_kind}")

    def _tool_python_scaffold(self, name: str) -> str:
        class_name = self._tool_scaffold_class_name(name)
        return (
            "from __future__ import annotations\n\n"
            "from typing import Any, Dict\n\n"
            "from pocketcode.core.interfaces import BaseTool\n\n\n"
            f"class {class_name}(BaseTool):\n"
            "    @property\n"
            "    def name(self) -> str:\n"
            f"        return \"{name}\"\n\n"
            "    @property\n"
            "    def description(self) -> str:\n"
            f"        return \"Workspace scaffold tool '{name}'.\"\n\n"
            "    @property\n"
            "    def schema(self) -> Dict[str, Any]:\n"
            "        return {\n"
            "            \"type\": \"object\",\n"
            "            \"properties\": {\n"
            "                \"text\": {\n"
            "                    \"type\": \"string\",\n"
            "                    \"description\": \"Input text for the scaffolded tool.\",\n"
            "                }\n"
            "            },\n"
            "            \"required\": [\"text\"],\n"
            "        }\n\n"
            "    def execute(self, **kwargs) -> Any:\n"
            "        text = str(kwargs.get(\"text\", \"\"))\n"
            "        return {\n"
            "            \"success\": True,\n"
            f"            \"message\": \"{name}: \" + text,\n"
            "        }\n"
        )

    def _tool_scaffold_class_name(self, name: str) -> str:
        parts = [part for part in str(name).replace("-", ".").replace("_", ".").split(".") if part]
        stem = "".join(part[:1].upper() + part[1:] for part in parts) or "WorkspaceTool"
        return f"{stem}Tool"

    def _clone_markdown_asset_contents(
        self,
        *,
        asset_kind: str,
        source_path: Path,
        source_text: str,
        new_name: str,
    ) -> tuple[str, str | None, Path | None]:
        front_matter, body = parse_markdown_front_matter(source_text)
        updated_front_matter = dict(front_matter)
        updated_front_matter["name"] = new_name

        companion_text: str | None = None
        companion_path: Path | None = None
        if asset_kind == "tool":
            handler_key = "handler" if updated_front_matter.get("handler") else "callable"
            handler_value = updated_front_matter.get(handler_key)
            if isinstance(handler_value, str) and ":" in handler_value:
                path_part, object_name = handler_value.split(":", 1)
                handler_path = Path(path_part)
                if not handler_path.is_absolute():
                    source_handler_path = (source_path.parent / handler_path).resolve()
                    if source_handler_path.exists():
                        source_base_name = self._asset_base_name_from_path(source_path, asset_kind="tool")
                        cloned_rel_path = handler_path.with_name(
                            self._rename_asset_related_filename(
                                filename=handler_path.name,
                                old_base=source_base_name,
                                new_base=new_name,
                            )
                        )
                        companion_path = (source_path.parent / cloned_rel_path).resolve()
                        companion_text = source_handler_path.read_text(encoding="utf-8")
                        cloned_rel_text = cloned_rel_path.as_posix()
                        if path_part.startswith("./") and not cloned_rel_text.startswith("./"):
                            cloned_rel_text = f"./{cloned_rel_text}"
                        updated_front_matter[handler_key] = f"{cloned_rel_text}:{object_name}"

        return (
            self._serialize_markdown_with_front_matter(updated_front_matter, body),
            companion_text,
            companion_path,
        )

    def _validate_markdown_asset_text(
        self,
        asset_kind: str,
        *,
        markdown_text: str,
        target_name: str,
        target_path: Path,
    ) -> str:
        front_matter, _ = parse_markdown_front_matter(markdown_text)
        raw_name = str(front_matter.get("name") or target_name).strip()
        if raw_name != target_name:
            raise ValueError(
                f"Markdown front matter name '{raw_name}' does not match target {asset_kind} '{target_name}'."
            )
        if asset_kind == "agent":
            self._validate_markdown_agent(markdown_text=markdown_text, target_path=target_path)
        if asset_kind == "flow":
            self._validate_markdown_flow(markdown_text=markdown_text, target_path=target_path)
        if asset_kind == "tool":
            self._validate_markdown_tool_handler(markdown_text=markdown_text, target_path=target_path)
        return raw_name

    def _validate_markdown_agent(self, *, markdown_text: str, target_path: Path) -> None:
        document = self._parse_workspace_markdown_asset_text_document(markdown_text, target_path=target_path)
        raw = compile_markdown_agent_definition(document, default_name=target_path.stem)

        flow_name = raw.get("flow") or raw.get("agent")
        base_agent = raw.get("base_agent") or raw.get("extends")
        flow_fields = {
            "vm_source",
            "vm_entry",
            "vm_module",
            "vm_modules",
            "vm_module_prefixes",
            "vm_file",
            "vm_files",
            "module",
            "entry_fn",
        }
        is_self_contained = any(field in raw for field in flow_fields)
        if not flow_name and not base_agent and not is_self_contained:
            raise ValueError(f"Markdown agent '{target_path}' is missing required field 'flow' or 'extends'.")
        if flow_name:
            validate_registry_reference(
                str(flow_name).strip(),
                allowed_kinds={"agent", "flow"},
                field_name=f"{target_path.name}: flow",
            )
            normalized_flow = normalize_registry_reference(str(flow_name).strip(), allowed_kinds={"agent", "flow"})
            self._validate_live_registry_reference(
                normalized_flow,
                registry=self._catalog.flows,
                allowed_kinds={"agent", "flow"},
                field_name=f"{target_path.name}: flow",
            )
        if base_agent:
            validate_registry_reference(
                str(base_agent).strip(),
                allowed_kinds={"agent", "flow"},
                field_name=f"{target_path.name}: extends",
            )
            normalized_base_agent = normalize_registry_reference(str(base_agent).strip(), allowed_kinds={"agent", "flow"})
            profile_manager = getattr(self, "_agent_profile_manager", None)
            base_exists = normalized_base_agent in getattr(self._catalog, "agents", {})
            if not base_exists and profile_manager is not None:
                base_exists = profile_manager.get(normalized_base_agent) is not None
            if not base_exists:
                raise ValueError(f"{target_path.name}: extends references unknown agent '{base_agent}'.")

        tools_raw = raw.get("tools")
        if tools_raw is not None:
            if not isinstance(tools_raw, list):
                raise ValueError(f"{target_path.name}: tools must be a list when provided.")
            self._validate_live_registry_reference_list(
                tools_raw,
                registry=self._catalog.tools,
                allowed_kinds={"tool"},
                field_name_prefix=f"{target_path.name}: tools",
            )

        hooks_raw = raw.get("hooks")
        if hooks_raw is not None:
            if not isinstance(hooks_raw, list):
                raise ValueError(f"{target_path.name}: hooks must be a list when provided.")
            self._validate_live_registry_reference_list(
                hooks_raw,
                registry=self._catalog.hooks,
                allowed_kinds={"hook"},
                field_name_prefix=f"{target_path.name}: hooks",
            )

        extra_prompts = raw.get("extra_prompts") or []
        if extra_prompts:
            if not isinstance(extra_prompts, list):
                raise ValueError(f"{target_path.name}: extra_prompts must be a list when provided.")
            for index, prompt_ref in enumerate(extra_prompts):
                if not isinstance(prompt_ref, str):
                    raise ValueError(f"{target_path.name}: extra_prompts[{index}] must be a string.")
                validate_prompt_source(prompt_ref, field_name=f"{target_path.name}: extra_prompts[{index}]")
                normalized_prompt = normalize_prompt_source(prompt_ref)
                self._validate_prompt_source_reference(
                    normalized_prompt,
                    source_path=target_path,
                    field_name=f"{target_path.name}: extra_prompts[{index}]",
                )

    def _validate_markdown_flow(self, *, markdown_text: str, target_path: Path) -> None:
        document = self._parse_workspace_markdown_asset_text_document(markdown_text, target_path=target_path)
        flow_definition = compile_markdown_flow_definition(document, default_name=target_path.stem)

        resolve_prompt_bundle(
            flow_definition,
            base_dir=target_path.parent,
            inline_keys=("system_prompt", "prompt"),
            file_keys=("system_prompt_file", "prompt_file"),
            files_key="prompt_files",
            default_files=[],
            fallback_dirs=self._workspace_prompt_fallback_dirs(),
            prompt_registry=getattr(self._catalog, "prompts", None),
            context_namespace=self._default_resource_context_namespace(),
        )

        self._validate_live_registry_reference_list(
            coerce_str_list(flow_definition.get("tools")),
            registry=self._catalog.tools,
            allowed_kinds={"tool"},
            field_name_prefix=f"{target_path.name}: tools",
        )

        self._validate_live_registry_reference_list(
            coerce_str_list(flow_definition.get("handoff_agents")),
            registry=self._catalog.flows,
            allowed_kinds={"agent", "flow"},
            field_name_prefix=f"{target_path.name}: handoff_agents",
        )

        self._validate_live_registry_reference_list(
            coerce_str_list(flow_definition.get("composite_agents")),
            registry=self._catalog.flows,
            allowed_kinds={"agent", "flow"},
            field_name_prefix=f"{target_path.name}: composite_agents",
        )

        metadata = flow_definition.get("metadata") or {}
        pass  # no graphs

    def _validate_markdown_tool_handler(self, *, markdown_text: str, target_path: Path) -> None:
        document = self._parse_workspace_markdown_asset_text_document(markdown_text, target_path=target_path)
        tool_definition = compile_markdown_tool_definition(document, default_name=target_path.stem)
        self._resolve_tool_handler_reference(tool_definition.handler, target_path.parent)

    def _parse_workspace_markdown_asset_text_document(
        self,
        markdown_text: str,
        *,
        target_path: Path,
    ):
        return parse_markdown_asset_text_document(
            markdown_text,
            source_path=target_path,
            expand_includes=True,
            fallback_dirs=self._workspace_prompt_fallback_dirs(),
            prompt_registry=getattr(self._catalog, "prompts", None),
            context_namespace=self._default_resource_context_namespace(),
        )

    def _workspace_prompt_fallback_dirs(self) -> tuple[Path, ...]:
        return (primary_resource_root(self._workspace_root).path / "prompts",)

    def _default_resource_context_namespace(self) -> str:
        return resource_root_namespace(primary_resource_root(self._workspace_root))

    def _validate_live_registry_reference(
        self,
        reference: str,
        *,
        registry: Any,
        allowed_kinds: set[str],
        field_name: str,
    ) -> str:
        validate_registry_reference(reference, allowed_kinds=allowed_kinds, field_name=field_name)
        normalized_reference = normalize_registry_reference(reference, allowed_kinds=allowed_kinds)
        self._qualify_registry_reference_or_raise(
            registry,
            normalized_reference,
            context_namespace=self._default_resource_context_namespace(),
            error_prefix=field_name,
        )
        return normalized_reference

    def _validate_live_registry_reference_list(
        self,
        references: list[Any],
        *,
        registry: Any,
        allowed_kinds: set[str],
        field_name_prefix: str,
    ) -> list[str]:
        normalized: list[str] = []
        for index, reference in enumerate(references):
            field_name = f"{field_name_prefix}[{index}]"
            if not isinstance(reference, str):
                raise ValueError(f"{field_name} must be a string.")
            normalized.append(
                self._validate_live_registry_reference(
                    reference,
                    registry=registry,
                    allowed_kinds=allowed_kinds,
                    field_name=field_name,
                )
            )
        return normalized

    def _qualify_registry_reference_or_raise(
        self,
        registry: Any,
        reference: str,
        *,
        context_namespace: str | None,
        error_prefix: str,
    ) -> str:
        try:
            return registry.qualify(reference, context_namespace=context_namespace)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"{error_prefix} could not be resolved: {reference} ({exc})") from exc

    def _validate_prompt_source_reference(self, prompt_ref: str, *, source_path: Path, field_name: str) -> None:
        if is_prompt_reference(prompt_ref):
            try:
                resolve_prompt_reference(
                    prompt_ref,
                    prompt_registry=getattr(self._catalog, "prompts", None),
                    context_namespace=self._default_resource_context_namespace(),
                )
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"{field_name} could not be resolved: {prompt_ref} ({exc})") from exc
            return

        try:
            load_prompt_markdown(
                base_dir=source_path.parent,
                prompt_file=prompt_ref,
                fallback_dirs=self._workspace_prompt_fallback_dirs(),
                prompt_registry=getattr(self._catalog, "prompts", None),
                context_namespace=self._default_resource_context_namespace(),
            )
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"{field_name} could not be resolved: {prompt_ref} ({exc})") from exc

    def _resolve_tool_handler_reference(self, handler_reference: str, base_dir: Path) -> Any:
        candidate = str(handler_reference or "").strip()
        if not candidate:
            raise ValueError("Markdown tool is missing required field 'handler'.")

        if ":" in candidate:
            path_part, object_name = candidate.split(":", 1)
            file_path = (base_dir / path_part).resolve()
            if not file_path.is_file():
                raise ValueError(f"Tool handler file not found: {file_path}")
            try:
                return self._load_object_from_file(file_path, object_name)
            except AttributeError as exc:
                raise ValueError(
                    f"Tool handler '{object_name}' was not found in {file_path}."
                ) from exc

        if "." not in candidate:
            raise ValueError(
                "Tool handler must be an import path (module.Object) or file reference (path.py:Object)."
            )

        module_name, object_name = candidate.rsplit(".", 1)
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Tool handler module import failed for '{module_name}': {exc}") from exc
        if not hasattr(module, object_name):
            raise ValueError(f"Tool handler '{object_name}' was not found in module '{module_name}'.")
        return getattr(module, object_name)

    def _load_object_from_file(self, file_path: Path, object_name: str) -> Any:
        module_name = self._build_dynamic_asset_module_name(file_path)
        sys.modules.pop(module_name, None)
        module = self._execute_dynamic_asset_module(file_path, module_name)
        return getattr(module, object_name)

    def _build_dynamic_asset_module_name(self, file_path: Path) -> str:
        content_hash = hash(file_path.read_bytes())
        token = f"{file_path.resolve()}:{content_hash}"
        return f"pocketcode_dynamic_asset_{abs(hash(token))}"

    def _execute_dynamic_asset_module(self, file_path: Path, module_name: str) -> types.ModuleType:
        module = types.ModuleType(module_name)
        module.__file__ = str(file_path)
        if file_path.name == "__init__.py":
            module.__package__ = module_name
            module.__path__ = [str(file_path.parent)]  # type: ignore[attr-defined]
        sys.modules[module_name] = module
        source = file_path.read_text(encoding="utf-8")
        code = compile(source, str(file_path), "exec")
        exec(code, module.__dict__)
        return module

    def _serialize_markdown_with_front_matter(self, front_matter: Dict[str, Any], body: str) -> str:
        front_matter_text = yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=False).strip()
        cleaned_body = str(body or "").rstrip()
        if cleaned_body:
            return f"---\n{front_matter_text}\n---\n{cleaned_body}\n"
        return f"---\n{front_matter_text}\n---\n"

    def _is_workspace_asset_path(self, path: Path) -> bool:
        resolved = Path(path).resolve()
        resource_roots = getattr(getattr(self, "_catalog", None), "resource_roots", None)
        if not resource_roots:
            resource_roots = [primary_resource_root(self._workspace_root)]
        return any(self._path_is_within(resolved, resource_root.path) for resource_root in resource_roots)

    def _path_is_within(self, path: Path, root: Path) -> bool:
        try:
            path.relative_to(Path(root).resolve())
            return True
        except ValueError:
            return False

    def _flow_markdown_path(self, flow_def: Any) -> Path | None:
        metadata = getattr(flow_def, "metadata", {}) or {}
        markdown_path = metadata.get("markdown_path")
        if not markdown_path:
            return None
        return Path(str(markdown_path)).resolve()

    def _tool_markdown_path(self, tool_impl: Any) -> Path | None:
        source_path = getattr(tool_impl, "_tool_source_path", None)
        if source_path is None:
            return None
        return Path(source_path).resolve()

    def _resolve_workspace_markdown_flow(self, name: str) -> tuple[Any, Path]:
        candidates: list[str] = []
        if "." in name and name in self._catalog.flows:
            candidates.append(name)
        else:
            candidates.extend(self._catalog.flows.owners_for(name))

        matches: list[tuple[Any, Path]] = []
        seen_paths: set[Path] = set()
        for qualified_name in candidates:
            flow_def = self._catalog.flows.get(qualified_name)
            if flow_def is None:
                continue
            path = self._flow_markdown_path(flow_def)
            if path is None or not self._is_workspace_asset_path(path):
                continue
            if path in seen_paths:
                continue
            seen_paths.add(path)
            matches.append((flow_def, path))

        if not matches:
            raise ValueError(f"Workspace markdown flow not found: {name}")
        if len(matches) > 1:
            raise ValueError(f"Ambiguous workspace markdown flow name: {name}")
        return matches[0]

    def _markdown_asset_filename(self, asset_kind: str, name: str) -> str:
        if asset_kind == "agent":
            return f"{name}.agent.md"
        if asset_kind == "tool":
            return f"{name}.tool.md"
        if asset_kind == "flow":
            return f"{name}.md"
        raise ValueError(f"Unsupported asset kind: {asset_kind}")

    def _workspace_markdown_asset_path(
        self,
        asset_kind: str,
        name: str,
        *,
        resource_root: Any | None = None,
    ) -> Path:
        normalized_kind = str(asset_kind or "").strip().lower()
        normalized_name = self._normalize_asset_file_name(name)
        active_resource_root = resource_root or primary_resource_root(self._workspace_root)
        base_path = active_resource_root.path
        if normalized_kind != "agent":
            return base_path / self._markdown_asset_filename(normalized_kind, normalized_name)

        parts = [part for part in normalized_name.split(".") if part]
        if not parts:
            raise ValueError("Agent name must not be empty.")
        group = parts[0]
        relative_parts = parts[1:] or [group]
        target_dir = base_path / f"agent.{group}"
        if len(relative_parts) > 1:
            target_dir = target_dir.joinpath(*relative_parts[:-1])
        return target_dir / f"{relative_parts[-1]}.agent.md"

    def _tool_handler_filename(self, name: str) -> str:
        return f"{name}.tool.py"

    def _tool_handler_path_from_markdown(self, markdown_path: Path, tool_impl: Any) -> Path | None:
        source_path = getattr(tool_impl, "_tool_source_path", None)
        if source_path is not None:
            try:
                front_matter, _body = parse_markdown_front_matter(markdown_path.read_text(encoding="utf-8"))
                handler_value = front_matter.get("handler") or front_matter.get("callable")
                if isinstance(handler_value, str) and ":" in handler_value:
                    path_part, _object_name = handler_value.split(":", 1)
                    handler_path = Path(path_part)
                    if not handler_path.is_absolute():
                        resolved = (markdown_path.parent / handler_path).resolve()
                        if resolved.exists():
                            return resolved
            except Exception:
                pass

        conventional_path = markdown_path.with_name(
            self._tool_handler_filename(self._asset_base_name_from_path(markdown_path, asset_kind="tool"))
        )
        return conventional_path if conventional_path.exists() else None

    def _asset_base_name_from_path(self, path: Path, *, asset_kind: str) -> str:
        name = Path(path).name
        if asset_kind == "agent" and name.endswith(".agent.md"):
            return name[: -len(".agent.md")]
        if asset_kind == "tool":
            if name.endswith(".tool.md"):
                return name[: -len(".tool.md")]
            if name.endswith(".tool.py"):
                return name[: -len(".tool.py")]
        if name.endswith(".md"):
            return name[: -len(".md")]
        return Path(path).stem

    def _rename_asset_related_filename(self, *, filename: str, old_base: str, new_base: str) -> str:
        if filename == old_base:
            return new_base
        if filename.startswith(f"{old_base}."):
            return f"{new_base}{filename[len(old_base):]}"
        return filename

    def _resolve_stackvm_flow_definition(self, name: str) -> tuple[str, FlowDefinition]:
        normalized_name = self._require_known_agent_name(name)
        definition = self._catalog.agents.get(normalized_name)
        if definition is None:
            raise ValueError(f"Unknown flow '{name}'.")
        if str(getattr(definition, "execution_mode", "")).strip().lower() != "vm":
            raise ValueError(f"Flow '{normalized_name}' is not StackVM-backed.")
        return normalized_name, definition

    def _resolve_stackvm_script_path(self, name_or_path: str, *, create_if_missing: bool = False) -> Path:
        raw_target = str(name_or_path or "").strip()
        if not raw_target:
            raise ValueError("StackVM script target must not be empty.")

        raw_path = Path(raw_target).expanduser()
        if raw_path.is_absolute() or "/" in raw_target or "\\" in raw_target:
            candidate = raw_path if raw_path.is_absolute() else (self._workspace_root / raw_path)
            if candidate.suffix.lower() not in {".vm", ".md"}:
                candidate = candidate.with_suffix(".vm")
            resolved = candidate.resolve()
            if resolved.is_file() or create_if_missing:
                return resolved
            raise ValueError(f"StackVM script not found: {resolved}")

        normalized_name = self._normalize_stackvm_script_name(raw_target)
        script_root = self._stackvm_script_root()
        direct_candidates = [
            (script_root / normalized_name).with_suffix(".vm"),
            (script_root / normalized_name).with_suffix(".md"),
        ]
        module_relative = Path(*[part for part in normalized_name.split(".") if part])
        module_candidates = [
            (script_root / module_relative).with_suffix(".vm"),
            (script_root / module_relative).with_suffix(".md"),
        ]
        for candidate in [*direct_candidates, *module_candidates]:
            resolved = candidate.resolve()
            if resolved.is_file():
                return resolved

        if create_if_missing:
            return direct_candidates[0].resolve()
        raise ValueError(f"StackVM script not found: {normalized_name}")

    def _stackvm_script_display_name(self, script_path: Path) -> str:
        try:
            return script_path.resolve().relative_to(self._stackvm_script_root()).as_posix()
        except ValueError:
            return str(script_path.resolve())

    def _stackvm_source_from_script_text(self, *, script_path: Path, source_text: str) -> str:
        if script_path.suffix.lower() != ".md":
            return str(source_text or "").strip()
        document = parse_markdown_asset_text_document(
            source_text,
            source_path=script_path,
        )
        vm_sections = [
            block.content.strip()
            for block in document.find_blocks(languages=("vm", "stackvm"))
            if block.content.strip()
        ]
        if vm_sections:
            return "\n\n".join(vm_sections).strip()
        return document.body.strip()

    def _stackvm_search_roots_for_definition(self, definition: FlowDefinition) -> list[Path]:
        metadata = dict(getattr(definition, "metadata", {}) or {})
        search_roots: list[Path] = []
        markdown_path = metadata.get("markdown_path")
        namespace_root = namespace_root_from_metadata(metadata)
        resource_root = metadata.get("resource_root")
        if markdown_path:
            search_roots.append(Path(str(markdown_path)).resolve().parent)
        if namespace_root is not None:
            search_roots.append(namespace_root)
        if resource_root:
            search_roots.append(Path(str(resource_root)).resolve())
        if not search_roots:
            search_roots.append(self._workspace_root)
        return list(dict.fromkeys(search_roots))

    def _load_and_compile_stackvm_flow(
        self,
        *,
        definition: FlowDefinition,
        entry: str | None = None,
    ) -> Dict[str, Any]:
        search_roots = self._stackvm_search_roots_for_definition(definition)
        source, source_files = load_stackvm_program_source(
            vm_source=definition.vm_source,
            vm_entry=entry or definition.vm_entry,
            vm_module=definition.vm_module,
            vm_modules=definition.vm_modules,
            vm_module_prefixes=definition.vm_module_prefixes,
            vm_file=definition.vm_file,
            vm_files=definition.vm_files,
            base_dir=search_roots[0],
            search_roots=search_roots,
        )
        return self._compile_stackvm_program(
            source=source,
            source_files=source_files,
            entry=entry or definition.vm_entry,
        )

    def _compile_stackvm_program(
        self,
        *,
        source: str,
        source_files: List[str],
        entry: str | None,
    ) -> Dict[str, Any]:
        compiled_source = str(source or "").strip()
        if not compiled_source and not entry:
            raise ValueError("StackVM target has no executable source or entry word.")

        warnings: list[dict[str, Any]] = []
        expanded_ast: list[Any] = []
        expansion_metadata = {
            "expansion_count": 0,
            "macro_names": [],
            "builtin_macro_names": [],
            "gensym_count": 0,
            "expansion_trace": [],
            "expansion_frames": [],
        }
        token_count = 0

        if compiled_source:
            source_ast = parse_stackvm_source(compiled_source)
            token_count = len(tokenize_stackvm_source(compiled_source))
            warnings = collect_stackvm_authoring_warnings(source_ast, source=compiled_source)
            expanded = expand_stackvm_source(compiled_source)
            validate_stackvm_ast(expanded.ast)
            expanded_ast = expanded.ast
            used_macro_names = list(dict.fromkeys(expanded.expansion_trace))
            builtin_macro_names = [
                name
                for name in used_macro_names
                if name in expanded.macros and expanded.macros[name].builtin
            ]
            expansion_metadata = {
                "expansion_count": expanded.expansion_count,
                "macro_names": used_macro_names,
                "builtin_macro_names": builtin_macro_names,
                "gensym_count": expanded.gensym_count,
                "expansion_trace": list(expanded.expansion_trace),
                "expansion_frames": [
                    {
                        "macro_name": frame.macro_name,
                        "builtin": frame.builtin,
                        "depth": frame.depth,
                        "call_site": frame.call_site,
                        "definition_site": frame.definition_site,
                        "generated_by": frame.generated_by,
                        "syntax_args": list(frame.syntax_args),
                        "expanded_form": frame.expanded_form,
                    }
                    for frame in expanded.expansion_frames
                ],
            }

        return {
            "source": compiled_source,
            "source_files": list(source_files),
            "expanded_source": serialize_stackvm_ast(expanded_ast) if expanded_ast else "",
            "expanded_ast": expanded_ast,
            "warnings": warnings,
            "warning_count": len(warnings),
            "expansion_metadata": expansion_metadata,
            "token_count": token_count,
        }

    def _run_stackvm_flow_definition(
        self,
        *,
        flow_name: str,
        definition: FlowDefinition,
        request: str,
        active_profile: Any,
        debug: bool,
        auto_confirm_tools: bool,
        entry_override: str | None = None,
    ) -> Dict[str, Any]:
        original_entry = definition.vm_entry
        if entry_override:
            definition.vm_entry = entry_override

        cli_context = {
            "files": set(),
            "folders": set(),
            "urls": set(),
            "snippets": {},
            "interface": "stackvm",
        }
        shared_store = self._build_shared_store(
            user_input=str(request or ""),
            cli_context=cli_context,
            event_handler=None,
            interaction_handler=None,
            run_handle=None,
        )
        shared_store["active_agent"] = flow_name
        shared_store["active_flow"] = flow_name
        shared_store["active_agent_profile"] = active_profile
        shared_store["stackvm_trace_enabled"] = bool(debug)
        shared_store["auto_confirm_tools"] = bool(auto_confirm_tools)

        try:
            self._agent_runtime.run(shared_store)
        finally:
            definition.vm_entry = original_entry

        summary = self._build_run_summary(shared_store, cli_context)
        self.last_run_summary = dict(summary)
        return {
            "target_kind": "agent" if active_profile is not None and getattr(active_profile, "name", None) else "flow",
            "flow": flow_name,
            "agent": getattr(active_profile, "name", None),
            "request": str(request or ""),
            "output": str(shared_store.get("final_output") or shared_store.get("final_answer") or ""),
            "final_answer": shared_store.get("final_answer"),
            "question_to_ask": shared_store.get("question_to_ask"),
            "error_message": shared_store.get("error_message"),
            "run_summary": summary,
            "trace": list(shared_store.get("vm_trace", [])),
            "trace_count": len(shared_store.get("vm_trace", [])),
            "last_vm_source": shared_store.get("last_vm_source", ""),
            "last_vm_expanded_source": shared_store.get("last_vm_expanded_source", ""),
            "last_vm_sources": list(shared_store.get("last_vm_sources", [])),
            "last_vm_expansion_metadata": dict(shared_store.get("last_vm_expansion_metadata", {})),
            "last_vm_validation_warnings": list(shared_store.get("last_vm_validation_warnings", [])),
            "pending_tool": shared_store.get("pending_tool"),
            "last_tool_result": shared_store.get("last_tool_result"),
            "tool_history": list(shared_store.get("tool_history", [])),
            "pending_handoff_agent": shared_store.get("pending_handoff_agent"),
            "results": dict(shared_store.get("results", {})) if isinstance(shared_store.get("results"), dict) else {},
        }

    def _run_stackvm_temp_script(
        self,
        *,
        script_path: Path,
        source_files: List[str],
        definition: FlowDefinition,
        active_profile: AgentProfile,
        request: str,
        debug: bool,
        auto_confirm_tools: bool,
    ) -> Dict[str, Any]:
        namespace = "__stackvm_cli__"
        flow_name = "script"
        qualified_name = f"{namespace}.{flow_name}"
        definition.name = flow_name
        definition.metadata = {
            **dict(definition.metadata or {}),
            "source_files": list(source_files),
        }
        active_profile.flow = qualified_name

        self._catalog.agents.unregister_namespace(namespace)
        self._catalog.agents.register(namespace, flow_name, definition)
        try:
            result = self._run_stackvm_flow_definition(
                flow_name=qualified_name,
                definition=definition,
                request=request,
                active_profile=active_profile,
                debug=debug,
                auto_confirm_tools=auto_confirm_tools,
                entry_override=definition.vm_entry,
            )
        finally:
            self._catalog.agents.unregister_namespace(namespace)

        result["target_kind"] = "script"
        result["name"] = self._stackvm_script_display_name(script_path)
        result["path"] = script_path
        result["flow"] = None
        return result

    def _resolve_workspace_markdown_tool(self, name: str) -> tuple[str, str, Any, Path]:
        candidates: list[str] = []
        if "." in name and name in self._catalog.tools:
            candidates.append(name)
        else:
            candidates.extend(self._catalog.tools.owners_for(name))

        matches: list[tuple[str, str, Any, Path]] = []
        seen_paths: set[Path] = set()
        for qualified_name in candidates:
            tool_impl = self._catalog.tools.get(qualified_name)
            if tool_impl is None:
                continue
            path = self._tool_markdown_path(tool_impl)
            if path is None or not self._is_workspace_asset_path(path):
                continue
            if path in seen_paths:
                continue
            seen_paths.add(path)
            _, _, local_name = qualified_name.partition(".")
            matches.append((qualified_name, local_name or qualified_name, tool_impl, path))

        if not matches:
            raise ValueError(f"Workspace markdown tool not found: {name}")
        if len(matches) > 1:
            raise ValueError(f"Ambiguous workspace markdown tool name: {name}")
        return matches[0]

    def delete_agent_profile(self, name: str) -> Path:
        target_path = self._agent_profile_manager.delete(name)
        if self.active_agent_profile is not None and self.active_agent_profile.name == name:
            self.active_agent_profile = None
        selection = self._textual_last_used_config(create=True)
        if selection.get("active_profile") == name:
            selection.pop("active_profile", None)
        self._cleanup_textual_profile_state(name)
        self._cleanup_invalid_textual_selection_presets(removed_profile=name)
        if self.current_agent:
            self._activate_default_profile_for(self.current_agent)
        return self._write_workspace_config()

    def delete_llm_profile(self, name: str) -> Path:
        profile = self.get_llm_profile(name)
        if profile is None or profile.get("source") != "workspace":
            raise ValueError(
                f"LLM profile '{name}' is not workspace-backed. Only workspace LLM profiles can be deleted."
            )
        target_path = self._workspace_llm_profile_manager.delete(name)
        if self.global_llm_override == name:
            self.global_llm_override = None
        selection = self._textual_last_used_config(create=True)
        if selection.get("global_llm_profile") == name:
            selection.pop("global_llm_profile", None)
        self._cleanup_invalid_textual_selection_presets(removed_llm=name)
        self._reload_llm_runtime()
        return self._write_workspace_config()

    def update_llm_profile(self, name: str, *, profile_config: Dict[str, Any]) -> Any:
        profile = self.get_llm_profile(name)
        if profile is None:
            raise ValueError(f"Unknown LLM profile '{name}'.")
        if profile.get("source") != "workspace":
            raise ValueError(
                f"LLM profile '{name}' is not workspace-backed. Clone it before editing."
            )
        self._workspace_llm_profile_manager.save(name, profile_config)
        self._reload_llm_runtime()
        return self.get_llm_profile(name)

    def update_agent_profile(
        self,
        name: str,
        *,
        llm_profile: Optional[str],
        tools: Optional[List[str]],
        extra_prompts: List[str],
        tool_confirmation_default: Optional[str],
        tool_confirmation_overrides: Optional[Dict[str, Optional[str]]] = None,
        skills: Any = _UNSET,
    ) -> Any:
        """Persist updates to a workspace-backed agent profile and refresh runtime state."""
        catalog = self._runtime_catalog()
        agents_registry = getattr(catalog, "agents", {})
        profile = self._base_agent_profile(name)
        if profile is None:
            raise ValueError(f"Unknown agent profile '{name}'.")
        if profile.source != "workspace" or profile.source_path is None:
            raise ValueError(
                f"Agent profile '{name}' is not workspace-backed. Clone it before editing."
            )
        if llm_profile:
            self._llm_router.resolve_profile_config(llm_profile)

        confirmation = dict(profile.tool_confirmation or {})
        if tool_confirmation_default is None:
            confirmation.pop("default", None)
        else:
            confirmation["default"] = self._normalize_confirmation_policy(tool_confirmation_default)
        if tool_confirmation_overrides is None:
            raw_overrides = dict(confirmation.get("overrides", {}))
        else:
            raw_overrides = dict(tool_confirmation_overrides)

        normalized_overrides = {
            tool_key: normalized
            for tool_name, policy in raw_overrides.items()
            if (tool_key := self._normalize_tool_key_for_persistence(tool_name))
            if (normalized := self._normalize_confirmation_policy(policy)) is not None
        }
        if normalized_overrides:
            confirmation["overrides"] = normalized_overrides
        elif "overrides" in confirmation:
            confirmation.pop("overrides", None)

        updated = dataclasses.replace(
            profile,
            llm_profile=llm_profile or None,
            skills=(
                self._normalize_skill_names(skills, strict=True)
                if skills is not _UNSET
                else (list(profile.skills) if profile.skills is not None else None)
            ),
            tools=self._normalize_tool_list(tools) if tools is not None else None,
            extra_prompts=self._normalize_prompt_sources(extra_prompts),
            tool_confirmation=confirmation,
        )
        self._agent_profile_manager.save(updated)
        self._agent_profile_manager.reload(dict(agents_registry))
        refreshed = self._resolved_agent_profile(name)
        if refreshed is not None and self.active_agent_profile and self.active_agent_profile.name == name:
            self.active_agent_profile = self._apply_session_profile_overrides(refreshed)
        return refreshed

    def save_agent_profile_skills(self, profile_name: str, skill_names: List[str]) -> Any:
        profile = self._base_agent_profile(profile_name)
        if profile is None:
            raise ValueError(f"Unknown agent profile '{profile_name}'.")
        normalized = self._normalize_skill_names(skill_names, strict=True)
        refreshed = self.update_agent_profile(
            profile_name,
            llm_profile=profile.llm_profile,
            tools=list(profile.tools) if profile.tools is not None else None,
            extra_prompts=list(profile.extra_prompts),
            tool_confirmation_default=(
                str(profile.tool_confirmation.get("default"))
                if isinstance(profile.tool_confirmation, dict) and profile.tool_confirmation.get("default")
                else None
            ),
            tool_confirmation_overrides=(
                self._normalized_confirmation_overrides(profile.tool_confirmation.get("overrides", {}))
                if isinstance(profile.tool_confirmation, dict)
                else {}
            ),
            skills=normalized,
        )
        self._clear_session_profile_skills_override(profile_name, normalized)
        self._refresh_active_profile(profile_name)
        return refreshed

    def save_agent_profile_tools(self, profile_name: str, tools: Optional[List[str]]) -> Any:
        profile = self._base_agent_profile(profile_name)
        if profile is None:
            raise ValueError(f"Unknown agent profile '{profile_name}'.")
        normalized_tools = self._normalize_tool_list(tools)
        refreshed = self.update_agent_profile(
            profile_name,
            llm_profile=profile.llm_profile,
            tools=normalized_tools,
            extra_prompts=list(profile.extra_prompts),
            tool_confirmation_default=(
                str(profile.tool_confirmation.get("default"))
                if isinstance(profile.tool_confirmation, dict) and profile.tool_confirmation.get("default")
                else None
            ),
            tool_confirmation_overrides=(
                self._normalized_confirmation_overrides(profile.tool_confirmation.get("overrides", {}))
                if isinstance(profile.tool_confirmation, dict)
                else {}
            ),
            skills=list(profile.skills) if profile.skills is not None else None,
        )
        self._clear_session_profile_tools_override(profile_name, normalized_tools)
        self._refresh_active_profile(profile_name)
        return refreshed

    def set_last_used_profile_tools(self, profile_name: str, tools: Optional[List[str]]) -> None:
        profile = self._base_agent_profile(profile_name)
        if profile is None and (self.active_agent_profile is None or self.active_agent_profile.name != profile_name):
            raise ValueError(f"Unknown agent profile '{profile_name}'.")
        normalized_tools = self._normalize_tool_list(tools)
        base_tools = self._base_tool_selection_for_profile(profile_name)
        if normalized_tools == base_tools:
            self.reset_last_used_profile_tools(profile_name)
            return
        profile_state = self._session_profile_state(profile_name, create=True)
        profile_state["tools"] = normalized_tools
        self._refresh_active_profile(profile_name)
        self._update_active_session_snapshot()

    def reset_last_used_profile_tools(self, profile_name: str) -> None:
        profile_state = self._session_profile_state(profile_name, create=True)
        profile_state.pop("tools", None)
        self._cleanup_session_profile_state(profile_name)
        self._refresh_active_profile(profile_name)
        self._update_active_session_snapshot()

    def set_last_used_profile_tool_policies(self, profile_name: str, overrides: Dict[str, Optional[str]]) -> None:
        profile = self._base_agent_profile(profile_name)
        if profile is None and (self.active_agent_profile is None or self.active_agent_profile.name != profile_name):
            raise ValueError(f"Unknown agent profile '{profile_name}'.")
        normalized_overrides = self._normalized_confirmation_overrides(overrides)
        base_overrides = (
            self._normalized_confirmation_overrides(profile.tool_confirmation.get("overrides", {}))
            if profile is not None and isinstance(profile.tool_confirmation, dict)
            else {}
        )
        if normalized_overrides == base_overrides:
            self.reset_last_used_profile_tool_policies(profile_name)
            return
        profile_state = self._session_profile_state(profile_name, create=True)
        profile_state["tool_confirmation_overrides"] = normalized_overrides
        self._refresh_active_profile(profile_name)
        self._update_active_session_snapshot()

    def reset_last_used_profile_tool_policies(self, profile_name: str) -> None:
        profile_state = self._session_profile_state(profile_name, create=True)
        profile_state.pop("tool_confirmation_overrides", None)
        self._cleanup_session_profile_state(profile_name)
        self._refresh_active_profile(profile_name)
        self._update_active_session_snapshot()

    def update_agent(
        self,
        name: str,
        *,
        llm_profile: Optional[str],
        tools: Optional[List[str]],
        extra_prompts: List[str],
        tool_confirmation_default: Optional[str],
        tool_confirmation_overrides: Optional[Dict[str, Optional[str]]] = None,
        skills: Any = _UNSET,
    ) -> Any:
        return self.update_agent_profile(
            name,
            llm_profile=llm_profile,
            tools=tools,
            extra_prompts=extra_prompts,
            tool_confirmation_default=tool_confirmation_default,
            tool_confirmation_overrides=tool_confirmation_overrides,
            skills=skills,
        )

    def list_tools_for_agent(
        self,
        agent_name: str,
        *,
        apply_active_profile: bool = False,
    ) -> List[str]:
        """Return tool names for an agent, optionally filtered by the active profile."""
        normalized_agent_name = self._require_known_agent_name(agent_name)
        if not apply_active_profile and normalized_agent_name in self._agent_tools_cache:
            return list(self._agent_tools_cache[normalized_agent_name])

        tool_names = list(self._catalog.resolve_tools_for_agent(normalized_agent_name))
        if apply_active_profile:
            active_profile = self.active_agent_profile
            if (
                active_profile is not None
                and self._normalize_agent_name(active_profile.flow) == normalized_agent_name
                and active_profile.tools is not None
            ):
                tool_names = [tool_name for tool_name in tool_names if tool_name in active_profile.tools]
            for tool_name in self._active_skill_existing_tool_refs():
                if tool_name not in tool_names:
                    tool_names.append(tool_name)
            for tool_name in self._active_skill_provided_tools().keys():
                if tool_name not in tool_names:
                    tool_names.append(tool_name)
        sorted_tool_names = sorted(tool_names)
        if not apply_active_profile:
            self._agent_tools_cache[normalized_agent_name] = list(sorted_tool_names)
        return sorted_tool_names

    def list_tools_for_flow(
        self,
        flow_name: str,
        *,
        apply_active_agent: bool = False,
    ) -> List[str]:
        return self.list_tools_for_agent(flow_name, apply_active_profile=apply_active_agent)

    def describe_agent(self, agent_name: Optional[str] = None) -> Dict[str, Any]:
        """Expose agent metadata for the control-oriented TUI."""
        target = agent_name or self.current_agent
        if not target:
            return {
                "name": None,
                "description": "",
                "execution_mode": "",
                "prompt_sources": [],
                "profiles": [],
                "tools": [],
            }
        normalized_target = self._require_known_agent_name(target)
        definition = self._catalog.agents.get(normalized_target)
        if definition is None:
            raise KeyError(f"Unknown agent '{target}'.")
        return {
            "name": normalized_target,
            "description": definition.description,
            "execution_mode": definition.execution_mode,
            "prompt_sources": list(definition.prompt_sources),
            "profiles": self.list_agent_profiles(normalized_target),
            "tools": self.list_tools_for_agent(normalized_target),
        }

    def describe_flow(self, flow_name: Optional[str] = None) -> Dict[str, Any]:
        return self.describe_agent(flow_name)

    def get_agent_prompt_sources(self, agent_name: Optional[str] = None) -> List[str]:
        """Return prompt source paths for the target agent."""
        target = agent_name or self.current_agent
        if not target:
            return []
        normalized_target = self._require_known_agent_name(target)
        definition = self._catalog.agents.get(normalized_target)
        if definition is None:
            raise KeyError(f"Unknown agent '{target}'.")
        return list(definition.prompt_sources)

    def get_flow_prompt_sources(self, flow_name: Optional[str] = None) -> List[str]:
        return self.get_agent_prompt_sources(flow_name)

    def _activate_default_profile_for(self, agent_name: str) -> None:
        """Set active_agent_profile to the agent's default profile."""
        profile = self._get_default_profile_for(agent_name)
        self.active_agent_profile = self._apply_session_profile_overrides(profile)

    def _get_default_profile_for(self, agent_name: str) -> Any:
        normalized_agent_name = self._normalize_agent_name(agent_name)
        if not normalized_agent_name:
            return None
        defn = self._catalog.agents.get(normalized_agent_name)
        if defn is None:
            return None
        explicit = getattr(defn, "default_agent_profile", None)
        if explicit is not None:
            default_name = explicit.name
        else:
            default_name = normalized_agent_name  # synthesised profile is named after the agent
        profile = self._resolved_agent_profile(default_name)
        if profile is None:
            # Fall back to any profile whose agent field matches.
            for raw_profile in self._agent_profile_manager.list():
                p = self._resolved_agent_profile(raw_profile.name)
                if p is None:
                    continue
                if self._normalize_agent_name(p.flow) == normalized_agent_name:
                    profile = p
                    break
        return profile

    def set_global_llm_override(self, profile_name: Optional[str]) -> None:
        if not profile_name:
            self.global_llm_override = None
            return
        self._llm_router.resolve_profile_config(profile_name)
        self.global_llm_override = profile_name

    def set_agent_llm_override(self, agent_name: str, profile_name: Optional[str]) -> None:
        normalized_agent_name = self._require_known_agent_name(agent_name)

        if not profile_name:
            self.agent_llm_overrides.pop(normalized_agent_name, None)
            return

        self._llm_router.resolve_profile_config(profile_name)
        self.agent_llm_overrides[normalized_agent_name] = profile_name

    def set_flow_llm_override(self, flow_name: str, profile_name: Optional[str]) -> None:
        self.set_agent_llm_override(flow_name, profile_name)

    def set_handoff_llm_override(
        self,
        source_agent: str,
        target_agent: str,
        profile_name: Optional[str],
    ) -> None:
        normalized_source_agent = self._require_known_agent_name(source_agent, label="source agent")
        normalized_target_agent = self._require_known_agent_name(target_agent, label="target agent")

        handoff_key = f"{normalized_source_agent}->{normalized_target_agent}"

        if not profile_name:
            self.handoff_llm_overrides.pop(handoff_key, None)
            return

        self._llm_router.resolve_profile_config(profile_name)
        self.handoff_llm_overrides[handoff_key] = str(profile_name)

    def describe_tools_for_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        normalized_agent_name = self._require_known_agent_name(agent_name)
        tool_names = self._catalog.resolve_tools_for_agent(normalized_agent_name)
        active_profile = self.active_agent_profile
        if (
            active_profile is not None
            and self._normalize_agent_name(active_profile.flow) == normalized_agent_name
            and active_profile.tools is not None
        ):
            tool_names = [tool_name for tool_name in tool_names if tool_name in active_profile.tools]
        for tool_name in self._active_skill_existing_tool_refs():
            if tool_name not in tool_names:
                tool_names.append(tool_name)
        for tool_name in self._active_skill_provided_tools().keys():
            if tool_name not in tool_names:
                tool_names.append(tool_name)
        return self._tool_runtime.describe_tools(tool_names)

    def describe_tools_for_flow(self, flow_name: str) -> List[Dict[str, Any]]:
        return self.describe_tools_for_agent(flow_name)

    def describe_tool(self, tool_name: str) -> Dict[str, Any]:
        return self._tool_runtime.describe_tool(tool_name)

    def start_request(
        self,
        user_input: str,
        cli_context: Dict[str, Any],
        *,
        bridge_user_input: bool = False,
        debug: bool = False,
    ) -> RunHandle:
        handle = RunHandle()
        shared_store = self._build_shared_store(
            user_input=user_input,
            cli_context=cli_context,
            event_handler=None,
            interaction_handler=handle.request_interaction if bridge_user_input else None,
            run_handle=handle,
        )
        initialize_runtime_observability(shared_store)
        handle.set_debug_snapshot_provider(
            lambda: self._build_live_debug_snapshot(shared_store=shared_store, cli_context=cli_context)
        )
        if debug:
            handle.enable_debugger(start_mode="step")
            for label in self._copy_session_debugger_breakpoints():
                predicate_config = build_debugger_predicate_from_label(label)
                if predicate_config is None:
                    continue
                predicate, normalized_label = predicate_config
                handle.add_debug_breakpoint(predicate, label=normalized_label)

        def emit_runtime_event(event_type: str, **payload: Any) -> None:
            annotated_payload = observe_runtime_event(shared_store, event_type, payload)
            handle.emit(event_type, **annotated_payload)

        shared_store["runtime_event_handler"] = emit_runtime_event

        def runner() -> None:
            try:
                emit_runtime_event(
                    "run_started",
                    request=user_input,
                    agent=shared_store.get("active_agent") or "auto",
                )
                result = self._execute_request(shared_store=shared_store, cli_context=cli_context)
                self._finalize_active_session(shared_store=shared_store, final_output=result)
                handle.complete(result=result, summary=self._build_run_summary(shared_store, cli_context))
            except RunCancelledError as exc:
                summary = self._build_run_summary(shared_store, cli_context)
                self.last_run_summary = dict(summary)
                self._finalize_active_session(shared_store=shared_store, cancellation_reason=str(exc))
                handle.cancelled(reason=str(exc), summary=summary)
            except Exception as exc:
                logger.error("Request processing failed: %s", exc, exc_info=True)
                self.last_run_summary = dict(self._build_run_summary(shared_store, cli_context))
                self._finalize_active_session(shared_store=shared_store, error=str(exc))
                handle.fail(exc)

        handle.start(runner)
        return handle

    def process_request(self, user_input: str, cli_context: Dict[str, Any]) -> str:
        return self.start_request(user_input=user_input, cli_context=cli_context).wait()

    def _build_shared_store(
        self,
        *,
        user_input: str,
        cli_context: Dict[str, Any],
        event_handler: Any = None,
        interaction_handler: Any = None,
        run_handle: RunHandle | None = None,
    ) -> Dict[str, Any]:
        initial_agent = self.current_agent or self._runtime_config.get("default_agent")
        if not initial_agent:
            agents = self.list_agents()
            if agents:
                initial_agent = agents[0]

        active_skills = self.get_active_skills() if hasattr(self, "get_active_skills") else []
        active_skill_existing_tool_refs = (
            self._active_skill_existing_tool_refs()
            if hasattr(self, "_active_skill_existing_tool_refs")
            else []
        )
        active_skill_tool_names = (
            list(self._active_skill_provided_tools().keys())
            if hasattr(self, "_active_skill_provided_tools")
            else []
        )

        shared_store: Dict[str, Any] = {
            "run_id": uuid4().hex,
            "initial_request": user_input,
            "workspace_root": str(self._workspace_root),
            "filesystem_root": str(self._workspace_root),
            "_session_manager": getattr(self, "_session_manager", None),
            "cli_context": self._copy_cli_context(cli_context),
            "formatted_cli_context": self._format_cli_context(cli_context),
            "active_flow": initial_agent,
            "active_agent": initial_agent,
            "default_llm_profile": self.default_llm_profile,
            "cli_llm_override": self.global_llm_override,
            "cli_agent_llm_overrides": dict(self.agent_llm_overrides),
            "cli_handoff_llm_overrides": dict(self.handoff_llm_overrides),
            "config_agent_llm_overrides": dict(self.config_llm_overrides.get("agents", {})),
            "config_handoff_llm_overrides": dict(self.config_llm_overrides.get("handoffs", {})),
            "auto_confirm_tools": self.auto_confirm_tools,
            "session_tool_confirmation": self._copy_session_confirmation_overrides(),
            # T013: inject active agent profile so AgentRuntime / ToolRuntime can read it.
            "active_agent_profile": self.active_agent_profile,
            "active_skills": active_skills,
            "active_skill_existing_tool_refs": active_skill_existing_tool_refs,
            "active_skill_tool_names": active_skill_tool_names,
            "active_session_id": getattr(self, "active_session_id", None),
            "active_session_title": getattr(self, "active_session_title", None),
            "active_session_loaded_from_history": bool(getattr(self, "active_session_loaded_from_history", False)),
            "replace_session_confirmation_overrides": self.replace_session_confirmation_overrides,
            "persist_tool_confirmation": self.set_persistent_tool_confirmation,
            "grant_session_profile_tool_access": self.grant_session_profile_tool_access,
        }
        if callable(event_handler):
            shared_store["runtime_event_handler"] = event_handler
        if callable(interaction_handler):
            shared_store["interaction_handler"] = interaction_handler
        if run_handle is not None:
            shared_store["run_cancel_requested"] = lambda: run_handle.is_cancel_requested
            shared_store["run_cancel_reason"] = lambda: run_handle.cancel_reason
        return shared_store

    def _execute_request(self, *, shared_store: Dict[str, Any], cli_context: Dict[str, Any]) -> str:
        self._agent_runtime.run(shared_store)

        if shared_store.get("active_agent"):
            self.current_agent = shared_store["active_agent"]

        self.last_run_summary = self._build_run_summary(shared_store, cli_context)

        return str(shared_store.get("final_output") or shared_store.get("final_answer") or "No output generated.")

    def _build_run_summary(self, shared_store: Dict[str, Any], cli_context: Dict[str, Any]) -> Dict[str, Any]:
        vm_validation_warnings = shared_store.get("last_vm_validation_warnings", {})
        if not isinstance(vm_validation_warnings, list):
            vm_validation_warnings = []
        return {
            "agent_path": self._build_agent_path(shared_store),
            "current_agent": shared_store.get("active_agent") or self.current_agent,
            "active_skills": [skill.name for skill in shared_store.get("active_skills", []) or []],
            "current_llm_profile": shared_store.get("last_llm_profile"),
            "current_llm_model": (
                shared_store.get("last_llm_generation", {}).get("model")
                if isinstance(shared_store.get("last_llm_generation"), dict)
                else None
            ),
            "llm_usage": dict(shared_store.get("llm_usage_totals", {}))
            if isinstance(shared_store.get("llm_usage_totals", {}), dict)
            else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "llm_cost_usd": float(shared_store.get("llm_cost_usd_total", 0.0)),
            "vm_validation_warnings": list(vm_validation_warnings),
            "vm_validation_warning_count": len(vm_validation_warnings),
            "last_runtime_effect": self._debug_snapshot_value(shared_store.get("last_runtime_effect")),
            "last_vm_effect": self._debug_snapshot_value(shared_store.get("last_vm_effect")),
            "last_vm_transition": shared_store.get("last_vm_transition"),
            "runtime_effect_count": len(shared_store.get("runtime_effect_history", []))
            if isinstance(shared_store.get("runtime_effect_history"), list)
            else 0,
            "runtime_effect_history": self._debug_snapshot_value(shared_store.get("runtime_effect_history", [])),
            "vm_effect_count": len(shared_store.get("vm_effect_history", []))
            if isinstance(shared_store.get("vm_effect_history"), list)
            else 0,
            "vm_effect_history": self._debug_snapshot_value(shared_store.get("vm_effect_history", [])),
            "context_stats": self._build_context_stats(cli_context),
            **build_runtime_observability_summary(shared_store),
        }

    def _build_live_debug_snapshot(
        self,
        *,
        shared_store: Dict[str, Any],
        cli_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "active_agent": shared_store.get("active_agent") or self.current_agent,
            "active_node_id": shared_store.get("active_node_id"),
            "active_node_kind": shared_store.get("active_node_kind"),
            "pending_tool": self._debug_snapshot_value(shared_store.get("pending_tool")),
            "pending_handoff_agent": shared_store.get("pending_handoff_agent"),
            "question_to_ask": shared_store.get("question_to_ask"),
            "final_answer": shared_store.get("final_answer"),
            "last_runtime_effect": self._debug_snapshot_value(shared_store.get("last_runtime_effect")),
            "last_vm_effect": self._debug_snapshot_value(shared_store.get("last_vm_effect")),
            "last_vm_transition": shared_store.get("last_vm_transition"),
            "runtime_effect_history": self._debug_snapshot_value(shared_store.get("runtime_effect_history", [])),
            "vm_effect_history": self._debug_snapshot_value(shared_store.get("vm_effect_history", [])),
            "error_message": shared_store.get("error_message"),
            "last_agent_decision": self._debug_snapshot_value(shared_store.get("last_agent_decision")),
            "last_tool_route": self._debug_snapshot_value(shared_store.get("last_tool_route")),
            "current_llm_profile": shared_store.get("last_llm_profile"),
            "current_llm_model": (
                shared_store.get("last_llm_generation", {}).get("model")
                if isinstance(shared_store.get("last_llm_generation"), dict)
                else None
            ),
            "llm_usage": dict(shared_store.get("llm_usage_totals", {}))
            if isinstance(shared_store.get("llm_usage_totals", {}), dict)
            else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "llm_cost_usd": float(shared_store.get("llm_cost_usd_total", 0.0)),
            "context_stats": self._build_context_stats(cli_context),
            **build_runtime_observability_summary(shared_store),
        }

    def _debug_snapshot_value(self, value: Any, *, depth: int = 0) -> Any:
        if depth >= 5:
            return repr(value)
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {
                str(key): self._debug_snapshot_value(item, depth=depth + 1)
                for key, item in list(value.items())[:16]
            }
        if isinstance(value, (list, tuple)):
            return [self._debug_snapshot_value(item, depth=depth + 1) for item in list(value)[:16]]
        return repr(value)

    def status(self) -> Dict[str, Any]:
        selected_agent = self.active_agent_profile.name if self.active_agent_profile else None
        selected_llm_profile = self._selected_llm_profile()
        runtime_flow = (
            self._runtime_config.get("agent_runtime_flow")
            or self._runtime_config.get("agent_runtime_workflow")
        )
        return {
            "flow": self.current_agent,
            "agent": selected_agent,
            "selected_flow": self.current_agent,
            "selected_agent": selected_agent,
            "selected_llm_profile": selected_llm_profile,
            "skills": list(self.enabled_skills),
            "runtime_flow": runtime_flow,
            # T013: expose active agent profile name.
            "active_agent_profile": selected_agent,
            "active_agent": selected_agent,
            "global_llm_override": self.global_llm_override,
            "agent_llm_overrides": dict(self.agent_llm_overrides),
            "handoff_llm_overrides": dict(self.handoff_llm_overrides),
            "config_llm_overrides": dict(self.config_llm_overrides),
            "default_llm_profile": self.default_llm_profile,
            "tool_confirmation": self._tool_confirmation_config,
            "session_tool_confirmation_overrides": self._copy_session_confirmation_overrides(),
            "session_debugger_breakpoints": self._copy_session_debugger_breakpoints(),
            "active_session_id": getattr(self, "active_session_id", None),
            "active_session_title": getattr(self, "active_session_title", None),
            "active_session_loaded_from_history": bool(getattr(self, "active_session_loaded_from_history", False)),
            "active_session": {
                "session_id": getattr(self, "active_session_id", None),
                "title": getattr(self, "active_session_title", None),
                "loaded_from_history": bool(getattr(self, "active_session_loaded_from_history", False)),
            },
            "available_flows": self.list_flows(),
            "available_agents": self.list_available_agents(),
            "available_skills": self.list_skills(),
            "available_llm_profiles": self.list_llm_profiles(),
            "last_run_summary": dict(self.last_run_summary),
            "session_profile_overrides": self._copy_session_profile_overrides(),
            "session_global_skills_override": list(getattr(self, "session_global_skills_override", None) or []),
        }

    def get_active_session_info(self) -> Dict[str, Any]:
        self._ensure_active_session()
        updated_at = None
        debugger_breakpoint_count = 0
        session_manager = getattr(self, "_session_manager", None)
        session_id = getattr(self, "active_session_id", None)
        if session_manager is not None and session_id:
            try:
                record = session_manager.load_session(session_id)
                updated_at = record.updated_at
                debugger_breakpoint_count = len(getattr(record, "debugger_breakpoints", []) or [])
            except Exception:
                updated_at = None
        return {
            "session_id": session_id,
            "title": getattr(self, "active_session_title", None),
            "updated_at": updated_at,
            "loaded_from_history": bool(getattr(self, "active_session_loaded_from_history", False)),
            "debugger_breakpoint_count": debugger_breakpoint_count,
        }

    def list_saved_sessions(self) -> List[Dict[str, Any]]:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            return []
        self._ensure_active_session()
        active_session_id = getattr(self, "active_session_id", None)
        items: list[Dict[str, Any]] = []
        for summary in session_manager.list_session_summaries():
            item = summary.as_dict()
            item["is_active"] = summary.session_id == active_session_id
            item["is_resumable"] = summary.session_id != active_session_id
            items.append(item)
        return items

    def get_saved_session_details(self, session_id: str | None = None) -> Dict[str, Any]:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            raise RuntimeError("Session persistence is not available.")
        self._ensure_active_session()
        target_id = str(session_id or getattr(self, "active_session_id", None) or "").strip()
        if not target_id:
            raise ValueError("Session id is required.")
        record = session_manager.load_session(target_id)
        return {
            "session_id": record.session_id,
            "title": record.title,
            "updated_at": record.updated_at,
            "created_at": record.created_at,
            "is_active": record.session_id == getattr(self, "active_session_id", None),
            "debugger_breakpoints": list(getattr(record, "debugger_breakpoints", []) or []),
            "debugger_breakpoint_count": len(getattr(record, "debugger_breakpoints", []) or []),
            "transcript_entries": len(getattr(record, "transcript", []) or []),
        }

    def start_new_session(self, title: str | None = None) -> Dict[str, Any]:
        self._update_active_session_snapshot()
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            raise RuntimeError("Session persistence is not available.")
        active_profile_name = self.active_agent_profile.name if self.active_agent_profile is not None else None
        current_agent_name = self.current_agent
        self.session_profile_overrides = {}
        self.session_global_skills_override = None
        self.clear_session_confirmation_overrides()
        self.clear_session_debugger_breakpoints(update_session=False)
        if active_profile_name:
            self.set_active_agent_profile(active_profile_name)
        elif current_agent_name:
            self.set_agent(current_agent_name)
        record = session_manager.create_session(title=title, state=self._session_state_payload())
        self.active_session_id = record.session_id
        self.active_session_title = record.title
        self.active_session_loaded_from_history = False
        return self.get_active_session_info()

    def resume_session(self, session_id: str) -> Dict[str, Any]:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            raise RuntimeError("Session persistence is not available.")

        record = session_manager.load_session(session_id)
        self._restore_saved_session(record)
        self.active_session_id = record.session_id
        self.active_session_title = record.title
        self.active_session_loaded_from_history = True
        self._update_active_session_snapshot()
        return self.get_active_session_info()

    def delete_session(self, session_id: str) -> Dict[str, Any]:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            raise RuntimeError("Session persistence is not available.")
        target_id = str(session_id or "").strip()
        if not target_id:
            raise ValueError("Session id is required.")
        if target_id == getattr(self, "active_session_id", None):
            raise ValueError("Cannot delete the active session.")
        if not session_manager.session_exists(target_id):
            raise ValueError(f"Unknown session '{target_id}'.")
        if not session_manager.delete_session(target_id):
            raise ValueError(f"Unknown session '{target_id}'.")
        return {"session_id": target_id, "deleted": True}

    def clear_saved_sessions(self) -> int:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            raise RuntimeError("Session persistence is not available.")
        self._ensure_active_session()
        active_session_id = getattr(self, "active_session_id", None)
        excluded = [active_session_id] if active_session_id else []
        return session_manager.clear_sessions(exclude_ids=excluded)

    def clear_saved_session_debugger_breakpoints(self, session_id: str | None = None) -> Dict[str, Any]:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            raise RuntimeError("Session persistence is not available.")
        self._ensure_active_session()
        target_id = str(session_id or getattr(self, "active_session_id", None) or "").strip()
        if not target_id:
            raise ValueError("Session id is required.")
        record = session_manager.load_session(target_id)
        prior = len(getattr(record, "debugger_breakpoints", []) or [])
        updated = session_manager.update_session(target_id, debugger_breakpoints=[])
        if updated.session_id == getattr(self, "active_session_id", None):
            self.session_debugger_breakpoints = []
        return {
            "session_id": updated.session_id,
            "cleared": prior,
        }

    def _selected_llm_profile(self) -> Optional[str]:
        if self.active_agent_profile is not None and self.active_agent_profile.llm_profile:
            return self.active_agent_profile.llm_profile
        return self.global_llm_override or self.default_llm_profile

    def set_session_confirmation_default(self, policy: Optional[str]) -> None:
        self.session_confirmation_overrides["default_policy"] = self._normalize_confirmation_policy(policy)

    def set_session_tool_confirmation(self, tool_name: str, policy: Optional[str]) -> None:
        self._set_policy_entry(self.session_confirmation_overrides["tool_policies"], tool_name, policy, kind="tool")

    def replace_session_confirmation_overrides(self, overrides: Dict[str, Any]) -> None:
        self.session_confirmation_overrides = self._normalize_session_confirmation_overrides(overrides)
        self._update_active_session_snapshot()

    def list_session_debugger_breakpoints(self) -> List[str]:
        return list(self._copy_session_debugger_breakpoints())

    def add_session_debugger_breakpoint(self, label: str) -> str:
        predicate_config = build_debugger_predicate_from_label(label)
        if predicate_config is None:
            raise ValueError("Invalid debugger breakpoint label.")
        _, normalized_label = predicate_config
        existing = self._copy_session_debugger_breakpoints()
        if normalized_label not in existing:
            existing.append(normalized_label)
            self.session_debugger_breakpoints = existing
            self._update_active_session_snapshot()
        return normalized_label

    def clear_session_debugger_breakpoint(self, label: str) -> bool:
        predicate_config = build_debugger_predicate_from_label(label)
        if predicate_config is None:
            return False
        _, normalized_label = predicate_config
        existing = self._copy_session_debugger_breakpoints()
        if normalized_label not in existing:
            return False
        self.session_debugger_breakpoints = [item for item in existing if item != normalized_label]
        self._update_active_session_snapshot()
        return True

    def clear_session_debugger_breakpoints(self, *, update_session: bool = True) -> int:
        count = len(self._copy_session_debugger_breakpoints())
        self.session_debugger_breakpoints = []
        if update_session:
            self._update_active_session_snapshot()
        return count

    def set_persistent_tool_confirmation(self, tool_name: str, policy: Optional[str]) -> Path:
        runtime_section = self._config.setdefault("runtime", {})
        if not isinstance(runtime_section, dict):
            runtime_section = {}
            self._config["runtime"] = runtime_section
        confirmation_section = runtime_section.setdefault("tool_confirmation", {})
        if not isinstance(confirmation_section, dict):
            confirmation_section = {}
            runtime_section["tool_confirmation"] = confirmation_section
        tool_policies = confirmation_section.setdefault("tool_policies", {})
        if not isinstance(tool_policies, dict):
            tool_policies = {}
            confirmation_section["tool_policies"] = tool_policies
        self._set_policy_entry(tool_policies, tool_name, policy, kind="tool")
        self._runtime_config = runtime_section
        self._tool_confirmation_config = self._build_tool_confirmation_config()
        self._refresh_runtime_components()
        return self._write_workspace_config()

    def set_session_agent_confirmation(self, agent_name: str, policy: Optional[str]) -> None:
        agent_entry = self._get_or_create_session_agent_entry(agent_name)
        normalized = self._normalize_confirmation_policy(policy)
        if normalized is None:
            agent_entry.pop("default_policy", None)
        else:
            agent_entry["default_policy"] = normalized
        self._cleanup_session_agent_entry(agent_name)

    def set_session_agent_tool_confirmation(self, agent_name: str, tool_name: str, policy: Optional[str]) -> None:
        agent_entry = self._get_or_create_session_agent_entry(agent_name)
        self._set_policy_entry(agent_entry.setdefault("tool_policies", {}), tool_name, policy, kind="tool")
        self._cleanup_session_agent_entry(agent_name)

    def clear_session_confirmation_overrides(self) -> None:
        self.session_confirmation_overrides = {
            "default_policy": None,
            "tool_policies": {},
            "agent_policies": {},
        }

    def _normalize_session_debugger_breakpoints(self, raw: Any) -> List[str]:
        normalized: list[str] = []
        if not isinstance(raw, list):
            return normalized
        for item in raw:
            predicate_config = build_debugger_predicate_from_label(str(item or ""))
            if predicate_config is None:
                continue
            _, label = predicate_config
            if label not in normalized:
                normalized.append(label)
        return normalized

    def _copy_session_debugger_breakpoints(self) -> List[str]:
        return self._normalize_session_debugger_breakpoints(
            getattr(self, "session_debugger_breakpoints", [])
        )

    def grant_session_profile_tool_access(self, profile_name: str, tool_name: str) -> Any:
        profile = self._base_agent_profile(profile_name)
        if profile is None:
            return self.active_agent_profile
        effective_profile = self.get_agent_profile(profile_name)
        current_tools = None if effective_profile is None else self._normalize_tool_list(effective_profile.tools)
        if current_tools is None:
            return effective_profile
        normalized_tool_name = self._normalize_tool_key_for_persistence(tool_name)
        if normalized_tool_name not in current_tools:
            self.set_last_used_profile_tools(profile_name, current_tools + [normalized_tool_name])
        return self.get_agent_profile(profile_name)

    def _restore_saved_session(self, record: Any) -> None:
        active_profile_name = str(getattr(record, "active_profile", "") or "").strip()
        active_agent_name = str(getattr(record, "active_agent", "") or "").strip()
        llm_profile_name = str(getattr(record, "global_llm_profile", "") or "").strip()
        self.session_profile_overrides = self._normalize_session_profile_overrides(
            getattr(record, "session_profile_overrides", {}) or {}
        )
        raw_global_skills = getattr(record, "session_global_skills_override", None)
        self.session_global_skills_override = (
            self._normalize_skill_names(list(raw_global_skills), strict=False)
            if isinstance(raw_global_skills, list)
            else None
        )

        self.active_agent_profile = None
        self.current_agent = None

        if active_profile_name:
            try:
                self.set_active_agent_profile(active_profile_name)
            except Exception:
                logger.warning("Saved session profile '%s' is unavailable; falling back.", active_profile_name)

        if self.active_agent_profile is None and active_agent_name:
            try:
                self.set_agent(active_agent_name)
            except Exception:
                logger.warning("Saved session agent '%s' is unavailable.", active_agent_name)

        self.enabled_skills = self._configured_enabled_skills(
            self.active_agent_profile.name if self.active_agent_profile is not None else None
        )

        try:
            self.set_global_llm_override(llm_profile_name or None)
        except Exception:
            logger.warning("Saved session LLM '%s' is unavailable; clearing override.", llm_profile_name)
            self.set_global_llm_override(None)

        self.replace_session_confirmation_overrides(
            dict(getattr(record, "session_confirmation_overrides", {}) or {})
        )
        self.session_debugger_breakpoints = self._normalize_session_debugger_breakpoints(
            getattr(record, "debugger_breakpoints", []) or []
        )
        self._refresh_runtime_components()

    def _copy_cli_context(self, cli_context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "files": sorted(list(cli_context.get("files", set()))),
            "folders": sorted(list(cli_context.get("folders", set()))),
            "urls": sorted(list(cli_context.get("urls", set()))),
            "snippets": dict(cli_context.get("snippets", {})),
        }

    def _build_tool_runtime(self) -> ToolRuntime:
        merged_tools = dict(self._catalog.tools.items())
        merged_tools.update(self._active_skill_provided_tools())
        return ToolRuntime(
            tools=merged_tools,
            require_confirmation=bool(self._runtime_config.get("require_tool_confirmation", True)),
            auto_approved_tools=list(self._runtime_config.get("auto_approved_tools", [])),
            confirmation_config=self._tool_confirmation_config,
        )

    def _active_skill_provided_tools(self) -> Dict[str, Any]:
        tools: Dict[str, Any] = {}
        for skill in self.get_active_skills():
            tools.update(skill.provided_tools)
        return tools

    def _active_skill_existing_tool_refs(self) -> List[str]:
        resolved: list[str] = []
        for skill in self.get_active_skills():
            for tool_ref in skill.tool_refs:
                qualified = self._qualify_tool_reference(
                    tool_ref,
                    context_agent=self.current_agent,
                )
                if qualified and qualified not in resolved:
                    resolved.append(qualified)
        return resolved

    def _qualify_tool_reference(
        self,
        tool_ref: str,
        *,
        context_agent: str | None,
    ) -> str | None:
        candidate = str(tool_ref or "").strip()
        if not candidate:
            return None
        if candidate.startswith("skill."):
            return candidate
        catalog = self._runtime_catalog()
        agents_registry = getattr(catalog, "agents", None)
        tools_registry = getattr(catalog, "tools", None)
        context_namespace = None
        if context_agent and agents_registry is not None:
            agent_definition = agents_registry.get(context_agent)
            if agent_definition is not None:
                metadata = agent_definition.metadata or {}
                context_namespace = metadata.get("namespace")
        try:
            if tools_registry is None:
                return candidate
            return tools_registry.qualify(candidate, context_namespace=context_namespace)
        except RegistryError as exc:
            raise ValueError(str(exc)) from exc

    def _build_tool_confirmation_config(self) -> Dict[str, Any]:
        section = self._runtime_config.get("tool_confirmation", {})
        if not isinstance(section, dict):
            section = {}
        return {
            "default_policy": section.get("default_policy"),
            "tool_policies": dict(section.get("tool_policies", {}))
            if isinstance(section.get("tool_policies", {}), dict)
            else {},
            "agent_policies": dict(section.get("agent_policies", {}))
            if isinstance(section.get("agent_policies", {}), dict)
            else {},
        }

    def _normalize_confirmation_policy(self, policy: Optional[str]) -> Optional[str]:
        if policy is None:
            return None
        normalized = str(policy).strip().lower()
        if normalized in {"allow", "confirm", "deny"}:
            return normalized
        raise ValueError(f"Invalid confirmation policy '{policy}'. Use allow|confirm|deny.")

    def _set_policy_entry(self, store: Dict[str, Any], key: str, policy: Optional[str], *, kind: str = "tool") -> None:
        normalized_key = (
            self._normalize_tool_key_for_persistence(key)
            if kind == "tool"
            else self._normalize_agent_key_for_persistence(key)
        )
        if not normalized_key:
            return
        normalized = self._normalize_confirmation_policy(policy)
        if normalized is None:
            store.pop(normalized_key, None)
        else:
            store[normalized_key] = normalized

    def _get_or_create_session_agent_entry(self, agent_name: str) -> Dict[str, Any]:
        agent_policies = self.session_confirmation_overrides.setdefault("agent_policies", {})
        normalized_agent_name = self._normalize_agent_key_for_persistence(agent_name)
        if not normalized_agent_name:
            return {"tool_policies": {}}
        entry = agent_policies.get(normalized_agent_name)
        if not isinstance(entry, dict):
            entry = {"tool_policies": {}}
            agent_policies[normalized_agent_name] = entry
        entry.setdefault("tool_policies", {})
        return entry

    def _cleanup_session_agent_entry(self, agent_name: str) -> None:
        agent_policies = self.session_confirmation_overrides.get("agent_policies", {})
        if not isinstance(agent_policies, dict):
            return
        normalized_agent_name = self._normalize_agent_key_for_persistence(agent_name)
        if not normalized_agent_name:
            return
        entry = agent_policies.get(normalized_agent_name)
        if not isinstance(entry, dict):
            return
        tool_policies = entry.get("tool_policies", {})
        if not isinstance(tool_policies, dict):
            tool_policies = {}
            entry["tool_policies"] = tool_policies

        has_default = "default_policy" in entry and entry.get("default_policy") is not None
        if not has_default and not tool_policies:
            agent_policies.pop(normalized_agent_name, None)

    def _normalize_session_confirmation_overrides(self, overrides: Any) -> Dict[str, Any]:
        source = overrides if isinstance(overrides, dict) else {}
        normalized = {
            "default_policy": self._normalize_confirmation_policy(source.get("default_policy"))
            if source.get("default_policy") is not None
            else None,
            "tool_policies": {},
            "agent_policies": {},
        }

        raw_tool_policies = source.get("tool_policies", {})
        if isinstance(raw_tool_policies, dict):
            for tool_name, policy in raw_tool_policies.items():
                try:
                    normalized_policy = self._normalize_confirmation_policy(policy)
                except ValueError:
                    continue
                normalized_tool_name = self._normalize_tool_key_for_persistence(tool_name)
                if normalized_policy is not None and normalized_tool_name:
                    normalized["tool_policies"][normalized_tool_name] = normalized_policy

        raw_agent_policies = source.get("agent_policies", {})
        if isinstance(raw_agent_policies, dict):
            for agent_name, entry in raw_agent_policies.items():
                if not isinstance(entry, dict):
                    continue
                normalized_agent_name = self._normalize_agent_key_for_persistence(agent_name)
                if not normalized_agent_name:
                    continue
                normalized_entry = {"default_policy": None, "tool_policies": {}}
                if entry.get("default_policy") is not None:
                    try:
                        normalized_entry["default_policy"] = self._normalize_confirmation_policy(entry.get("default_policy"))
                    except ValueError:
                        normalized_entry["default_policy"] = None
                raw_entry_tools = entry.get("tool_policies", {})
                if isinstance(raw_entry_tools, dict):
                    for tool_name, policy in raw_entry_tools.items():
                        try:
                            normalized_policy = self._normalize_confirmation_policy(policy)
                        except ValueError:
                            continue
                        normalized_tool_name = self._normalize_tool_key_for_persistence(tool_name)
                        if normalized_policy is not None and normalized_tool_name:
                            normalized_entry["tool_policies"][normalized_tool_name] = normalized_policy
                if normalized_entry["default_policy"] is not None or normalized_entry["tool_policies"]:
                    normalized["agent_policies"][normalized_agent_name] = normalized_entry

        return normalized

    def _copy_session_confirmation_overrides(self) -> Dict[str, Any]:
        return self._normalize_session_confirmation_overrides(self.session_confirmation_overrides)

    def _copy_session_profile_overrides(self) -> Dict[str, Any]:
        copied: Dict[str, Any] = {}
        session_profile_overrides = getattr(self, "session_profile_overrides", {})
        for profile_name, raw_state in session_profile_overrides.items():
            if not isinstance(raw_state, dict):
                continue
            state: Dict[str, Any] = {}
            if "tools" in raw_state:
                tools = raw_state.get("tools")
                state["tools"] = self._normalize_tool_list(tools) if isinstance(tools, list) else None
            if "skills" in raw_state and isinstance(raw_state.get("skills"), list):
                state["skills"] = self._normalize_skill_names(list(raw_state.get("skills", [])), strict=False)
            if "tool_confirmation_overrides" in raw_state:
                state["tool_confirmation_overrides"] = self._normalized_confirmation_overrides(
                    raw_state.get("tool_confirmation_overrides", {})
                )
            if state:
                copied[profile_name] = state
        return copied

    def _normalize_session_profile_overrides(self, raw: Any) -> Dict[str, Dict[str, Any]]:
        if not isinstance(raw, dict):
            return {}
        normalized: Dict[str, Dict[str, Any]] = {}
        for profile_name, raw_state in raw.items():
            clean_name = str(profile_name).strip()
            if not clean_name or not isinstance(raw_state, dict):
                continue
            state: Dict[str, Any] = {}
            if "tools" in raw_state:
                tools = raw_state.get("tools")
                state["tools"] = self._normalize_tool_list(tools) if isinstance(tools, list) else None
            if "skills" in raw_state and isinstance(raw_state.get("skills"), list):
                state["skills"] = self._normalize_skill_names(list(raw_state.get("skills", [])), strict=False)
            if "tool_confirmation_overrides" in raw_state:
                state["tool_confirmation_overrides"] = self._normalized_confirmation_overrides(
                    raw_state.get("tool_confirmation_overrides", {})
                )
            if state:
                normalized[clean_name] = state
        return normalized

    def _session_state_payload(self, shared_store: Dict[str, Any] | None = None) -> Dict[str, Any]:
        source = shared_store or {}
        active_profile = source.get("active_agent_profile", self.active_agent_profile)
        active_skills = source.get("active_skills")
        if active_skills is None:
            active_skills = self.get_active_skills()
        skill_names = [
            skill.name if hasattr(skill, "name") else str(skill)
            for skill in active_skills or []
        ]
        return {
            "active_agent": self._normalize_agent_key_for_persistence(source.get("active_agent") or self.current_agent),
            "active_profile": getattr(active_profile, "name", None),
            "enabled_skills": skill_names,
            "global_llm_profile": source.get("cli_llm_override") or self.global_llm_override,
            "session_global_skills_override": list(getattr(self, "session_global_skills_override", None) or []),
            "session_profile_overrides": self._copy_session_profile_overrides(),
            "session_confirmation_overrides": self._normalize_session_confirmation_overrides(
                source.get("session_tool_confirmation")
                if isinstance(source.get("session_tool_confirmation"), dict)
                else self._copy_session_confirmation_overrides()
            ),
            "debugger_breakpoints": self._copy_session_debugger_breakpoints(),
        }

    def _ensure_active_session(self) -> None:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            return
        session_id = getattr(self, "active_session_id", None)
        if session_id:
            try:
                record = session_manager.load_session(session_id)
            except Exception:
                logger.warning("Active session '%s' could not be loaded; creating a fresh session.", session_id)
            else:
                self.active_session_title = record.title
                return
        record = session_manager.create_session(state=self._session_state_payload())
        self.active_session_id = record.session_id
        self.active_session_title = record.title
        self.active_session_loaded_from_history = False

    def _update_active_session_snapshot(self, shared_store: Dict[str, Any] | None = None) -> None:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            return
        self._ensure_active_session()
        session_id = getattr(self, "active_session_id", None)
        if not session_id:
            return
        record = session_manager.update_session(session_id, **self._session_state_payload(shared_store))
        self.active_session_title = record.title

    def _finalize_active_session(
        self,
        *,
        shared_store: Dict[str, Any],
        final_output: str | None = None,
        error: str | None = None,
        cancellation_reason: str | None = None,
    ) -> None:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            return
        self._update_active_session_snapshot(shared_store)
        session_id = getattr(self, "active_session_id", None)
        if not session_id:
            return

        run_id = str(shared_store.get("run_id") or "") or None
        initial_request = str(shared_store.get("initial_request") or "").strip()
        if initial_request:
            session_manager.append_transcript_entry(
                session_id,
                role="user",
                content=initial_request,
                run_id=run_id,
                metadata={"agent": shared_store.get("active_agent")},
            )

        transcript_payload = None
        transcript_role = "assistant"
        if final_output:
            transcript_payload = str(final_output)
        elif cancellation_reason:
            transcript_role = "system"
            transcript_payload = f"Run cancelled: {cancellation_reason}"
        elif error:
            transcript_role = "system"
            transcript_payload = f"Run failed: {error}"

        if transcript_payload:
            session_manager.append_transcript_entry(
                session_id,
                role=transcript_role,
                content=transcript_payload,
                run_id=run_id,
                metadata={"summary": dict(self.last_run_summary)},
            )

        event_handler = shared_store.get("runtime_event_handler")
        if callable(event_handler):
            saved_record = session_manager.load_session(session_id)
            event_handler(
                "session_saved",
                session_id=session_id,
                title=saved_record.title,
                transcript_entries=len(saved_record.transcript),
            )

    def _build_llm_overrides_config(self) -> Dict[str, Dict[str, str]]:
        runtime_overrides = self._runtime_config.get("llm_overrides", {})
        if not isinstance(runtime_overrides, dict):
            return {"agents": {}, "handoffs": {}}

        agent_map: Dict[str, str] = {}
        raw_agents = runtime_overrides.get("agents", {})
        if isinstance(raw_agents, dict):
            for agent_name, profile_name in raw_agents.items():
                if isinstance(agent_name, str) and isinstance(profile_name, str):
                    agent_map[agent_name.strip()] = profile_name.strip()

        handoff_map: Dict[str, str] = {}
        raw_handoffs = runtime_overrides.get("handoffs", {})
        if isinstance(raw_handoffs, dict):
            for key, value in raw_handoffs.items():
                if isinstance(key, str) and isinstance(value, str):
                    handoff_map[key.strip()] = value.strip()
                    continue

                if isinstance(key, str) and isinstance(value, dict):
                    source_agent = key.strip()
                    for target_agent, profile_name in value.items():
                        if isinstance(target_agent, str) and isinstance(profile_name, str):
                            handoff_map[f"{source_agent}->{target_agent.strip()}"] = profile_name.strip()

        return {
            "agents": agent_map,
            "handoffs": handoff_map,
        }

    def _merged_llm_profiles(self) -> Dict[str, Dict[str, Any]]:
        merged = dict(self._catalog.llm_profiles)
        merged.update(self._workspace_llm_profile_manager.list_profiles())
        return merged

    def _reload_llm_runtime(self) -> None:
        self._workspace_llm_profile_manager.load()
        self._llm_router = LlmRouter(config=self._config, resource_root_llm_profiles=self._merged_llm_profiles())
        self.default_llm_profile = (
            self._llm_config.get("default_profile")
            or self._llm_router.default_profile_name
        )
        self.config_llm_overrides = self._build_llm_overrides_config()
        self._refresh_runtime_components()

    def _format_cli_context(self, cli_context_data: Dict[str, Any]) -> str:
        if not cli_context_data or not any(cli_context_data.values()):
            return "None provided."

        lines: List[str] = []
        files = cli_context_data.get("files") or set()
        folders = cli_context_data.get("folders") or set()
        urls = cli_context_data.get("urls") or set()
        snippets = cli_context_data.get("snippets") or {}

        if files:
            lines.append("Files:")
            lines.extend(f"- {item}" for item in sorted(list(files)))
        if folders:
            lines.append("Folders:")
            lines.extend(f"- {item}" for item in sorted(list(folders)))
        if urls:
            lines.append("URLs:")
            lines.extend(f"- {item}" for item in sorted(list(urls)))
        if snippets:
            lines.append("Snippets:")
            for name, content in sorted(snippets.items()):
                lines.append(f"- {name}: {content}")

        return "\n".join(lines) if lines else "None provided."

    def _build_context_stats(self, cli_context_data: Dict[str, Any]) -> Dict[str, int]:
        files = cli_context_data.get("files") or set()
        folders = cli_context_data.get("folders") or set()
        urls = cli_context_data.get("urls") or set()
        snippets = cli_context_data.get("snippets") or {}
        snippet_chars = 0
        if isinstance(snippets, dict):
            for value in snippets.values():
                if isinstance(value, str):
                    snippet_chars += len(value)
        return {
            "files": len(files),
            "folders": len(folders),
            "urls": len(urls),
            "snippets": len(snippets) if isinstance(snippets, dict) else 0,
            "snippet_chars": snippet_chars,
        }

    def _maybe_refresh_runtime_components(self) -> None:
        if not hasattr(self, "_catalog") or not hasattr(self._catalog, "tools"):
            return
        required_attrs = ("_runtime_config", "_tool_confirmation_config", "_llm_router")
        if not all(hasattr(self, attr_name) for attr_name in required_attrs):
            return
        self._refresh_runtime_components()

    def _refresh_runtime_components(self) -> None:
        self._tool_runtime = self._build_tool_runtime()
        self._agent_runtime = AgentRuntime(
            catalog=self._catalog,
            llm_router=self._llm_router,
            tool_runtime=self._tool_runtime,
            runtime_config=self._runtime_config,
        )

    def _restore_textual_selection_state(self) -> None:
        snapshot = self._current_last_used_selection_snapshot()
        selected_profile = str(snapshot.get("active_profile") or "").strip()
        selected_llm = str(snapshot.get("global_llm_profile") or "").strip()
        session_default = snapshot.get("session_confirmation_default")

        if "auto_confirm_tools" in snapshot:
            self.auto_confirm_tools = bool(snapshot.get("auto_confirm_tools"))

        if session_default is not None:
            self.set_session_confirmation_default(session_default)

        if selected_profile and self._base_agent_profile(selected_profile) is not None:
            self.set_active_agent_profile(selected_profile)

        if selected_llm:
            try:
                self.set_global_llm_override(selected_llm)
            except Exception:
                logger.warning("Ignoring missing last-used LLM profile '%s'.", selected_llm)

    def _write_workspace_config(self) -> Path:
        config_path = self._workspace_root / WORKSPACE_SETTINGS_FILENAME
        config_path.write_text(
            yaml.safe_dump(self._config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return config_path

    def _textual_config(self, *, create: bool) -> Dict[str, Any]:
        if not hasattr(self, "_config") or not isinstance(self._config, dict):
            self._config = {}
        runtime_section = self._config.setdefault("runtime", {}) if create else self._config.get("runtime", {})
        if not isinstance(runtime_section, dict):
            runtime_section = {}
            if create:
                self._config["runtime"] = runtime_section
        textual = runtime_section.get("textual", {})
        if not isinstance(textual, dict):
            textual = {}
            if create:
                runtime_section["textual"] = textual
        elif create:
            runtime_section["textual"] = textual
        return textual

    def _textual_last_used_config(self, *, create: bool) -> Dict[str, Any]:
        textual = self._textual_config(create=create)
        last_used = textual.get("last_used", {})
        if not isinstance(last_used, dict):
            last_used = {}
            if create:
                textual["last_used"] = last_used
        elif create:
            textual["last_used"] = last_used
        return last_used

    def _textual_selection_presets_config(self, *, create: bool) -> Dict[str, Any]:
        textual = self._textual_config(create=create)
        presets = textual.get("selection_presets", {})
        if not isinstance(presets, dict):
            presets = {}
            if create:
                textual["selection_presets"] = presets
        elif create:
            textual["selection_presets"] = presets
        return presets

    def _capture_textual_selection_snapshot(self) -> Dict[str, Any]:
        snapshot: Dict[str, Any] = {}
        if self.active_agent_profile is not None:
            snapshot["active_profile"] = self.active_agent_profile.name
        if self.global_llm_override:
            snapshot["global_llm_profile"] = self.global_llm_override
        session_global_skills_override = getattr(self, "session_global_skills_override", None)
        if session_global_skills_override is not None:
            snapshot["skills"] = list(session_global_skills_override)
        session_default = self.session_confirmation_overrides.get("default_policy")
        if session_default is not None:
            snapshot["session_confirmation_default"] = session_default
        snapshot["auto_confirm_tools"] = bool(self.auto_confirm_tools)
        agent_profiles = self._copy_session_profile_overrides()
        if self.active_agent_profile is not None:
            current_skills = self._normalize_skill_names(list(getattr(self, "enabled_skills", []) or []), strict=False)
            base_skills = self._base_skill_selection_for_profile(self.active_agent_profile.name)
            if current_skills and current_skills != base_skills:
                agent_profiles.setdefault(self.active_agent_profile.name, {})["skills"] = current_skills
        if agent_profiles:
            snapshot["agent_profiles"] = agent_profiles
        return snapshot

    def _normalize_textual_selection_snapshot(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        snapshot: Dict[str, Any] = {}
        active_profile = str(raw.get("active_profile") or "").strip()
        if active_profile:
            snapshot["active_profile"] = active_profile
        global_llm_profile = str(raw.get("global_llm_profile") or "").strip()
        if global_llm_profile:
            snapshot["global_llm_profile"] = global_llm_profile
        if isinstance(raw.get("skills"), list):
            snapshot["skills"] = self._normalize_skill_names(list(raw.get("skills", [])), strict=False)
        session_default = self._normalize_confirmation_policy(raw.get("session_confirmation_default"))
        if session_default is not None:
            snapshot["session_confirmation_default"] = session_default
        if "auto_confirm_tools" in raw:
            snapshot["auto_confirm_tools"] = bool(raw.get("auto_confirm_tools"))
        raw_agent_profiles = raw.get("agent_profiles", {})
        if isinstance(raw_agent_profiles, dict):
            cleaned_profiles: Dict[str, Any] = {}
            for profile_name, state in raw_agent_profiles.items():
                cleaned_name = str(profile_name).strip()
                if not cleaned_name or not isinstance(state, dict):
                    continue
                cleaned_state: Dict[str, Any] = {}
                if "tools" in state:
                    tools = state.get("tools")
                    cleaned_state["tools"] = self._normalize_tool_list(tools) if isinstance(tools, list) else None
                if "skills" in state and isinstance(state.get("skills"), list):
                    cleaned_state["skills"] = self._normalize_skill_names(list(state.get("skills", [])), strict=False)
                if "tool_confirmation_overrides" in state:
                    cleaned_state["tool_confirmation_overrides"] = self._normalized_confirmation_overrides(
                        state.get("tool_confirmation_overrides", {})
                    )
                if cleaned_state:
                    cleaned_profiles[cleaned_name] = cleaned_state
            if cleaned_profiles:
                snapshot["agent_profiles"] = cleaned_profiles
        return snapshot

    def _current_last_used_selection_snapshot(self) -> Dict[str, Any]:
        last_used = self._textual_last_used_config(create=False)
        if not isinstance(last_used, dict):
            return {}
        return self._normalize_textual_selection_snapshot(last_used)

    def _replace_last_used_selection_snapshot(self, snapshot: Dict[str, Any]) -> None:
        normalized = self._normalize_textual_selection_snapshot(snapshot)
        last_used = self._textual_last_used_config(create=True)
        for key in (
            "active_profile",
            "global_llm_profile",
            "skills",
            "session_confirmation_default",
            "auto_confirm_tools",
            "agent_profiles",
        ):
            if key in normalized:
                value = normalized[key]
                last_used[key] = copy.deepcopy(value) if isinstance(value, dict) else value
            else:
                last_used.pop(key, None)
        self.enabled_skills = self._normalize_skill_names(normalized.get("skills", []), strict=False)
        self._refresh_runtime_components()
        self._cleanup_textual_last_used_config()

    def _cleanup_invalid_textual_selection_presets(
        self,
        *,
        removed_profile: str | None = None,
        removed_llm: str | None = None,
    ) -> None:
        presets = self._textual_selection_presets_config(create=False)
        if not presets:
            return
        for preset_name, raw_snapshot in list(presets.items()):
            if not isinstance(raw_snapshot, dict):
                presets.pop(preset_name, None)
                continue
            snapshot = self._normalize_textual_selection_snapshot(raw_snapshot)
            if removed_profile:
                if snapshot.get("active_profile") == removed_profile:
                    snapshot.pop("active_profile", None)
                agent_profiles = snapshot.get("agent_profiles")
                if isinstance(agent_profiles, dict):
                    agent_profiles.pop(removed_profile, None)
                    if not agent_profiles:
                        snapshot.pop("agent_profiles", None)
            if removed_llm and snapshot.get("global_llm_profile") == removed_llm:
                snapshot.pop("global_llm_profile", None)
            presets[preset_name] = snapshot

    def _textual_profile_state(self, profile_name: str, *, create: bool) -> Dict[str, Any]:
        last_used = self._textual_last_used_config(create=create)
        agent_profiles = last_used.get("agent_profiles", {})
        if not isinstance(agent_profiles, dict):
            agent_profiles = {}
            if create:
                last_used["agent_profiles"] = agent_profiles
        elif create:
            last_used["agent_profiles"] = agent_profiles
        profile_state = agent_profiles.get(profile_name, {})
        if not isinstance(profile_state, dict):
            profile_state = {}
            if create:
                agent_profiles[profile_name] = profile_state
        elif create:
            agent_profiles[profile_name] = profile_state
        return profile_state

    def _cleanup_textual_profile_state(self, profile_name: str) -> None:
        last_used = self._textual_last_used_config(create=False)
        agent_profiles = last_used.get("agent_profiles", {})
        if not isinstance(agent_profiles, dict):
            return
        profile_state = agent_profiles.get(profile_name)
        if isinstance(profile_state, dict) and not profile_state:
            agent_profiles.pop(profile_name, None)
        if not agent_profiles:
            last_used.pop("agent_profiles", None)
        self._cleanup_textual_last_used_config()

    def _cleanup_textual_last_used_config(self) -> None:
        textual = self._textual_config(create=False)
        last_used = textual.get("last_used", {})
        if isinstance(last_used, dict) and not last_used:
            textual.pop("last_used", None)

    def _configured_global_skills(self) -> List[str]:
        if not hasattr(self, "_skill_manager"):
            return []
        textual = self._textual_config(create=False)
        default_skills = textual.get("default_skills", []) if isinstance(textual, dict) else []
        return self._normalize_skill_names(default_skills, strict=False)

    def _base_skill_selection_for_profile(self, profile_name: str | None = None) -> List[str]:
        target_profile = str(
            profile_name
            or getattr(getattr(self, "active_agent_profile", None), "name", "")
            or ""
        ).strip()
        if target_profile:
            profile = self._base_agent_profile(target_profile)
            if profile is not None and getattr(profile, "skills", None) is not None:
                return self._normalize_skill_names(getattr(profile, "skills", []), strict=False)
        return self._configured_global_skills()

    def _configured_enabled_skills(self, profile_name: str | None = None) -> List[str]:
        target_profile = str(
            profile_name
            or getattr(getattr(self, "active_agent_profile", None), "name", "")
            or ""
        ).strip()
        if target_profile:
            profile_state = self._session_profile_state(target_profile, create=False)
            if isinstance(profile_state.get("skills"), list):
                return self._normalize_skill_names(profile_state.get("skills", []), strict=False)
            return self._base_skill_selection_for_profile(target_profile)
        session_global_skills_override = getattr(self, "session_global_skills_override", None)
        if session_global_skills_override is not None:
            return list(session_global_skills_override)
        return self._configured_global_skills()

    def _normalize_skill_names(self, skill_names: List[str], *, strict: bool) -> List[str]:
        normalized: list[str] = []
        for raw_name in skill_names or []:
            skill_name = str(raw_name).strip()
            if not skill_name:
                continue
            if self._skill_manager.get(skill_name) is None:
                if strict:
                    raise ValueError(f"Unknown skill '{skill_name}'. Available: {self.list_skills()}")
                continue
            if skill_name not in normalized:
                normalized.append(skill_name)
        return normalized

    def _normalize_tool_list(self, tools: Optional[List[str]]) -> Optional[List[str]]:
        if tools is None:
            return None
        normalized: list[str] = []
        for raw_name in tools:
            tool_name = self._normalize_tool_key_for_persistence(raw_name)
            if tool_name and tool_name not in normalized:
                normalized.append(tool_name)
        return sorted(normalized)

    def _normalized_confirmation_overrides(self, overrides: Any) -> Dict[str, str]:
        if not isinstance(overrides, dict):
            return {}
        normalized: Dict[str, str] = {}
        for tool_name, policy in overrides.items():
            tool_key = self._normalize_tool_key_for_persistence(tool_name)
            if not tool_key:
                continue
            normalized_policy = self._normalize_confirmation_policy(policy)
            if normalized_policy is not None:
                normalized[tool_key] = normalized_policy
        return normalized

    def _normalize_prompt_sources(self, prompt_refs: List[str]) -> List[str]:
        normalized: list[str] = []
        for prompt_ref in prompt_refs or []:
            candidate = normalize_prompt_source(str(prompt_ref))
            if candidate and candidate not in normalized:
                normalized.append(candidate)
        return normalized

    def _normalize_tool_key_for_persistence(self, tool_name: Any) -> str:
        return normalize_registry_reference(tool_name, allowed_kinds={"tool"})

    def _normalize_agent_key_for_persistence(self, agent_name: Any) -> str:
        normalized = self._normalize_agent_name(agent_name)
        return str(normalized).strip() if normalized else ""

    def _base_agent_profile(self, name: str) -> Any:
        manager = getattr(self, "_agent_profile_manager", None)
        if manager is not None:
            profile = manager.get(name)
            if profile is not None:
                return profile
        active_profile = getattr(self, "active_agent_profile", None)
        if active_profile is not None and getattr(active_profile, "name", None) == name:
            return active_profile
        return None

    def _resolved_agent_profile(self, name: str) -> Any:
        manager = getattr(self, "_agent_profile_manager", None)
        if manager is not None and hasattr(manager, "resolve"):
            profile = manager.resolve(name)
            if profile is not None:
                return profile
        return self._base_agent_profile(name)

    def _base_tool_selection_for_profile(self, profile_name: str) -> Optional[List[str]]:
        profile = self._base_agent_profile(profile_name)
        if profile is None:
            return None
        return self._normalize_tool_list(profile.tools)

    def _session_profile_state(self, profile_name: str, *, create: bool) -> Dict[str, Any]:
        session_profile_overrides = getattr(self, "session_profile_overrides", None)
        if not isinstance(session_profile_overrides, dict):
            session_profile_overrides = {}
            setattr(self, "session_profile_overrides", session_profile_overrides)
        profile_state = session_profile_overrides.get(profile_name, {})
        if not isinstance(profile_state, dict):
            profile_state = {}
        if create:
            session_profile_overrides[profile_name] = profile_state
        return profile_state

    def _cleanup_session_profile_state(self, profile_name: str) -> None:
        session_profile_overrides = getattr(self, "session_profile_overrides", None)
        if not isinstance(session_profile_overrides, dict):
            return
        profile_state = session_profile_overrides.get(profile_name)
        if isinstance(profile_state, dict) and not profile_state:
            session_profile_overrides.pop(profile_name, None)

    def _apply_session_profile_overrides(self, profile: AgentProfile | None) -> AgentProfile | None:
        if profile is None:
            return None
        profile_state = self._session_profile_state(profile.name, create=False)
        if not profile_state:
            return profile

        tools = list(profile.tools) if profile.tools is not None else None
        if "tools" in profile_state:
            raw_tools = profile_state.get("tools")
            tools = self._normalize_tool_list(raw_tools) if isinstance(raw_tools, list) else None

        confirmation = copy.deepcopy(profile.tool_confirmation or {})
        if "tool_confirmation_overrides" in profile_state:
            overrides = self._normalized_confirmation_overrides(profile_state.get("tool_confirmation_overrides", {}))
            if overrides:
                confirmation["overrides"] = overrides
            else:
                confirmation.pop("overrides", None)

        return dataclasses.replace(
            profile,
            tools=tools,
            extra_prompts=list(profile.extra_prompts),
            tool_confirmation=confirmation,
        )

    def _refresh_active_profile(self, profile_name: str) -> None:
        if self.active_agent_profile is None or self.active_agent_profile.name != profile_name:
            return
        resolved_profile = self._resolved_agent_profile(profile_name)
        if resolved_profile is None:
            return
        self.active_agent_profile = self._apply_session_profile_overrides(resolved_profile)
        self.enabled_skills = self._configured_enabled_skills(profile_name)
        self._maybe_refresh_runtime_components()

    def _clear_session_profile_skills_override(self, profile_name: str, skill_names: List[str]) -> None:
        profile_state = self._session_profile_state(profile_name, create=False)
        if not profile_state:
            return
        if self._normalize_skill_names(profile_state.get("skills", []), strict=False) != list(skill_names):
            return
        profile_state.pop("skills", None)
        self._cleanup_session_profile_state(profile_name)
        self._update_active_session_snapshot()

    def _clear_session_profile_tools_override(self, profile_name: str, tools: Optional[List[str]]) -> None:
        profile_state = self._session_profile_state(profile_name, create=False)
        if not profile_state or "tools" not in profile_state:
            return
        raw_tools = profile_state.get("tools")
        profile_tools = self._normalize_tool_list(raw_tools) if isinstance(raw_tools, list) else None
        if profile_tools != self._normalize_tool_list(tools):
            return
        profile_state.pop("tools", None)
        self._cleanup_session_profile_state(profile_name)
        self._update_active_session_snapshot()

    def _build_agent_path(self, shared_store: Dict[str, Any]) -> List[str]:
        trace = shared_store.get("agent_trace", [])
        if not isinstance(trace, list):
            trace = []

        ordered_agents: List[str] = []
        for item in trace:
            if not isinstance(item, dict):
                continue
            name = item.get("agent")
            if isinstance(name, str) and name and (not ordered_agents or ordered_agents[-1] != name):
                ordered_agents.append(name)

        handoff_history = shared_store.get("handoff_history", [])
        if isinstance(handoff_history, list):
            for handoff_agent in handoff_history:
                if isinstance(handoff_agent, str) and handoff_agent and (not ordered_agents or ordered_agents[-1] != handoff_agent):
                    ordered_agents.append(handoff_agent)

        return ordered_agents
