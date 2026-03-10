from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false

from contextlib import contextmanager
import re
from typing import Any, Callable, Dict, Iterable, Iterator

from textual.widgets import Input
import yaml

from pocketcode.cli.runtime_events import format_runtime_event
from pocketcode.cli.user_interaction import describe_interaction_request, interaction_placeholder

from .picker_screens import AssetPickerScreen
from .shared import PickerOption, TEXTUAL_VIEWS, WORKSPACE_VIEWS
from .store import OutputBlock, SetCurrentViewAction, SetRightPanelVisibleAction, SetWorkspaceViewAction


class TextualAppRenderingMixin:
    _CODE_BLOCK_PATTERN = re.compile(r"```(?P<language>[^\n`]*)\n(?P<code>.*?)```", re.DOTALL)

    def _render_profile_policy_summary(self, overrides: dict[str, str]) -> str:
        if not overrides:
            return "No per-tool confirmation overrides. Tools inherit the agent default."
        lines = ["Per-tool confirmation overrides:"]
        for tool_name in sorted(overrides):
            lines.append(f"- {tool_name}: {overrides[tool_name]}")
        return "\n".join(lines)

    def _apply_ui_commit(
        self,
        *,
        hydrate_engine: bool = False,
        refresh_suggestions: bool = False,
    ) -> None:
        if refresh_suggestions:
            self._refresh_suggestions()
        if hydrate_engine:
            self._hydrate_cli_state_from_engine()
        self._apply_ui_state(self._build_ui_state())

    def _commit_ui_update(
        self,
        *,
        hydrate_engine: bool = False,
        refresh_suggestions: bool = False,
    ) -> None:
        if self._ui_commit_batch_depth > 0:
            self._ui_commit_requested = True
            self._ui_commit_refresh_suggestions = self._ui_commit_refresh_suggestions or refresh_suggestions
            self._ui_commit_hydrate_engine = self._ui_commit_hydrate_engine or hydrate_engine
            return
        self._apply_ui_commit(
            hydrate_engine=hydrate_engine,
            refresh_suggestions=refresh_suggestions,
        )

    def _commit_engine_ui_update(
        self,
        *,
        refresh_suggestions: bool = False,
    ) -> None:
        self._commit_ui_update(
            hydrate_engine=True,
            refresh_suggestions=refresh_suggestions,
        )

    @contextmanager
    def _batch_ui_update(
        self,
        *,
        commit: bool = True,
        hydrate_engine: bool = False,
        refresh_suggestions: bool = False,
    ) -> Iterator[None]:
        self._ui_commit_batch_depth += 1
        if commit:
            self._ui_commit_requested = True
        self._ui_commit_refresh_suggestions = self._ui_commit_refresh_suggestions or refresh_suggestions
        self._ui_commit_hydrate_engine = self._ui_commit_hydrate_engine or hydrate_engine
        try:
            yield
        finally:
            self._ui_commit_batch_depth -= 1
            if self._ui_commit_batch_depth == 0 and self._ui_commit_requested:
                pending_hydrate_engine = self._ui_commit_hydrate_engine
                pending_refresh_suggestions = self._ui_commit_refresh_suggestions
                self._ui_commit_requested = False
                self._ui_commit_hydrate_engine = False
                self._ui_commit_refresh_suggestions = False
                self._apply_ui_commit(
                    hydrate_engine=pending_hydrate_engine,
                    refresh_suggestions=pending_refresh_suggestions,
                )

    @contextmanager
    def _batch_engine_ui_update(
        self,
        *,
        commit: bool = True,
        refresh_suggestions: bool = False,
    ) -> Iterator[None]:
        with self._batch_ui_update(
            commit=commit,
            hydrate_engine=True,
            refresh_suggestions=refresh_suggestions,
        ):
            yield

    def _refresh_ui(self) -> None:
        self._commit_ui_update()

    def _write_info(self, text: str) -> None:
        self._append_output_block(OutputBlock(kind="info", text=str(text), title="Info"))
        self._sync_output_widget()

    def _write_error(self, text: str) -> None:
        self._append_output_block(OutputBlock(kind="error", text=str(text), title="Error"))
        self._sync_output_widget()

    def _write_runtime(self, text: str) -> None:
        self._append_output_block(OutputBlock(kind="runtime", text=str(text), title="Runtime"))
        self._sync_output_widget()

    def _write_user(self, text: str) -> None:
        self._append_output_block(OutputBlock(kind="user", text=str(text), title="You"))
        self._sync_output_widget()

    def _single_line_preview(self, value: Any, *, limit: int = 96) -> str:
        text = str(value or "").strip().replace("\r", "")
        if not text:
            return "(empty)"
        first_line = text.splitlines()[0].strip()
        if len(first_line) <= limit:
            return first_line
        return first_line[: limit - 3].rstrip() + "..."

    def _write_tool_policy_request(self, event: Dict[str, Any]) -> None:
        tool_name = str(event.get("tool") or "tool")
        question = str(event.get("prompt") or f"Allow tool '{tool_name}'?")
        arguments = event.get("arguments")
        arguments_text = self._serialize_output_payload(arguments) or "{}"
        self._append_output_block(
            OutputBlock(
                kind="tool_call",
                title=f"Tool Policy: {tool_name}",
                text=f"{question}\n\nArgs:\n{arguments_text}",
                summary_text=f"{question} | args",
                language="yaml" if isinstance(arguments, (dict, list, tuple)) else None,
            ),
            plain_text=f"runtime> Tool confirmation requested: {question}",
        )
        self._sync_output_widget()

    def _write_llm_request(self, event: Dict[str, Any]) -> None:
        agent_name = str(event.get("agent") or "unknown")
        profile_name = str(event.get("profile") or "default")
        prompt_text = str(event.get("prompt_text") or "")
        prompt_preview = self._single_line_preview(prompt_text)
        self._append_output_block(
            OutputBlock(
                kind="code",
                title=f"LLM Request: {agent_name}",
                text=prompt_text or "(empty prompt)",
                summary_text=f"{profile_name}: {prompt_preview}",
                language="text",
            ),
            plain_text=f"runtime> LLM request ({profile_name}): {prompt_preview}",
        )
        self._sync_output_widget()

    def _write_llm_response(self, event: Dict[str, Any]) -> None:
        agent_name = str(event.get("agent") or "unknown")
        model_name = str(event.get("model") or "-")
        usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
        total_tokens = int(usage.get("total_tokens", 0) or 0) if isinstance(usage, dict) else 0
        response_text = str(event.get("response_text") or "")
        response_preview = self._single_line_preview(response_text)
        self._append_output_block(
            OutputBlock(
                kind="code",
                title=f"LLM Response: {agent_name}",
                text=response_text or "(empty response)",
                summary_text=f"{model_name} | {total_tokens} tokens | {response_preview}",
                language="text",
            ),
            plain_text=f"runtime> LLM response ({model_name}, {total_tokens} tokens): {response_preview}",
        )
        self._sync_output_widget()

    def _write_assistant(self, text: str) -> None:
        response_text = str(text)
        self._append_output_blocks(
            self._build_assistant_output_blocks(response_text),
            plain_text=f"assistant> {response_text}",
            assistant_response=response_text,
        )
        self._sync_output_widget()

    def _write_tool_call(self, tool_name: str, arguments: Any) -> None:
        argument_text = self._serialize_output_payload(arguments)
        text = argument_text if argument_text else "No arguments provided."
        self._append_output_block(
            OutputBlock(kind="tool_call", text=text, title=f"Tool Call: {tool_name}"),
            plain_text=f"tool> {tool_name}({argument_text})" if argument_text else f"tool> {tool_name}()",
        )
        self._sync_output_widget()

    def _write_tool_result(self, tool_name: str, result: Any, *, success: bool) -> None:
        rendered = self._serialize_output_payload(result)
        language = "yaml" if isinstance(result, (dict, list, tuple)) else None
        status_text = "succeeded" if success else "failed"
        self._append_output_block(
            OutputBlock(
                kind="tool_result",
                text=rendered or "No result returned.",
                title=f"Tool Result: {tool_name} ({status_text})",
                language=language,
            ),
            plain_text=f"tool-result> {tool_name}: {rendered or status_text}",
        )
        self._sync_output_widget()

    def _serialize_output_payload(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (dict, list, tuple)):
            dumped = yaml.safe_dump(value, sort_keys=False, allow_unicode=False).strip()
            return dumped or repr(value)
        return repr(value)

    def _build_assistant_output_blocks(self, text: str) -> list[OutputBlock]:
        matches = list(self._CODE_BLOCK_PATTERN.finditer(text))
        if not matches:
            return [OutputBlock(kind="assistant", text=text, title="Assistant")]

        blocks: list[OutputBlock] = []
        cursor = 0
        for match in matches:
            prose = text[cursor : match.start()].strip()
            if prose:
                blocks.append(OutputBlock(kind="assistant", text=prose, title="Assistant"))

            language = str(match.group("language") or "text").strip() or "text"
            code = str(match.group("code") or "").strip("\n")
            if code:
                title = "Diff" if language.lower() == "diff" else f"Code ({language})"
                blocks.append(OutputBlock(kind="code", text=code, title=title, language=language))
            cursor = match.end()

        trailing = text[cursor:].strip()
        if trailing:
            blocks.append(OutputBlock(kind="assistant", text=trailing, title="Assistant"))
        return blocks or [OutputBlock(kind="assistant", text=text, title="Assistant")]

    def _write_event_output(self, event: Dict[str, Any], message: str) -> None:
        event_type = str(event.get("type") or "")
        if event_type == "tool_confirmation_requested":
            self._write_tool_policy_request(event)
            return
        if event_type == "llm_call_started":
            self._write_llm_request(event)
            return
        if event_type == "llm_call_completed":
            self._write_llm_response(event)
            return
        if event_type == "tool_started":
            self._write_tool_call(str(event.get("tool") or "tool"), event.get("arguments"))
            return
        if event_type == "tool_finished":
            self._write_tool_result(
                str(event.get("tool") or "tool"),
                event.get("result"),
                success=bool(event.get("success")),
            )
            return
        if event_type == "runtime_error":
            self._write_error(str(event.get("message") or message))
            return
        self._write_runtime(message)

    def _set_current_view(self, view_name: str, *, announce: bool = False, refresh: bool = True) -> None:
        if view_name not in TEXTUAL_VIEWS:
            raise ValueError(f"Unknown view '{view_name}'. Available: {sorted(TEXTUAL_VIEWS)}")
        if view_name == self._cli_state.current_view:
            return
        self._set_cli_current_view(view_name)
        if announce:
            self._write_info(f"View: {TEXTUAL_VIEWS[view_name]['label']}.")
        if refresh:
            self._refresh_ui()

    def _apply_workspace_view(
        self,
        view_name: str,
        *,
        announce: bool,
        preserve_current_view: bool = False,
    ) -> None:
        config = WORKSPACE_VIEWS.get(view_name)
        if config is None:
            return
        target_view = str(config["view"])
        if target_view not in TEXTUAL_VIEWS:
            return
        actions = [
            SetWorkspaceViewAction(workspace_view=view_name),
            SetRightPanelVisibleAction(visible=bool(config["right"])),
        ]
        if not preserve_current_view:
            actions.append(SetCurrentViewAction(current_view=target_view))
        self._dispatch_cli_actions(*actions)
        if announce:
            self._write_info(f"Workspace View: {config['label']}.")

    def _set_main_input_placeholder(self, prompt: str | None = None) -> None:
        input_widget = self.query_one("#main-input", Input)
        self._set_runtime_input_placeholder(prompt)
        input_widget.placeholder = self._runtime_state.main_input_placeholder

    def _profile_cycle(self) -> list[str]:
        profile_names: list[str] = []
        for agent_name in self._engine.list_agents():
            profile_names.extend(self._engine.list_agent_profiles(agent_name))
        return profile_names

    def _remember_run_event(self, text: str) -> None:
        self._remember_runtime_event(text)

    def _drain_run_events(self) -> None:
        events = self._drain_active_run_effect()
        should_refresh = False
        for event in events:
            should_refresh = self._consume_run_event(event) or should_refresh
        should_refresh = self._sync_textual_debugger_state() or should_refresh
        if should_refresh:
            self._refresh_ui()

    def _consume_run_event(self, event: Dict[str, Any]) -> bool:
        event_type = str(event.get("type") or "")
        message = self._format_runtime_event(event)
        if message:
            self._remember_run_event(message)
            if event_type not in {"run_completed", "run_failed"}:
                self._write_event_output(event, message)

        if event_type == "interaction_requested":
            self._set_pending_input_request(event)
            self._set_runtime_status("waiting_for_input")
            self._set_main_input_placeholder(interaction_placeholder(event))
            if event.get("kind") != "text":
                self._write_info(describe_interaction_request(event))
            if getattr(self, "_control_presentation", "inline") != "modal":
                self._show_inline_pending_input(dict(event))
            self.call_after_refresh(lambda: self._present_pending_input_modal(dict(event)))
            return True
        if event_type == "interaction_received":
            self._set_runtime_status("running")
            self._set_main_input_placeholder()
            return True
        if event_type == "user_input_requested":
            self._set_pending_input_request(event)
            self._set_runtime_status("waiting_for_input")
            self._set_main_input_placeholder(str(event.get("prompt") or "Provide input"))
            if getattr(self, "_control_presentation", "inline") != "modal":
                self._show_inline_pending_input(dict(event))
            self.call_after_refresh(lambda: self._present_pending_input_modal(dict(event)))
            return True
        if event_type == "user_input_received":
            self._set_runtime_status("running")
            self._set_main_input_placeholder()
            return True
        if event_type == "run_completed":
            with self._batch_engine_ui_update():
                self._textual_debugger_active = False
                self._textual_debugger_last_pause_key = None
                self._debugger_inline_breakpoint_visible = False
                if self._runtime_state.pending_input_request is not None and not getattr(self, "_inline_prompt_resolved", False):
                    self._clear_inline_prompt_display()
                self._set_runtime_busy(False)
                self._active_run = None
                self._set_pending_input_request(None)
                self._set_runtime_status("idle")
                self._set_main_input_placeholder()
                self._write_assistant(str(event.get("output") or ""))
            return False
        if event_type == "run_failed":
            with self._batch_engine_ui_update():
                self._textual_debugger_active = False
                self._textual_debugger_last_pause_key = None
                self._debugger_inline_breakpoint_visible = False
                if self._runtime_state.pending_input_request is not None and not getattr(self, "_inline_prompt_resolved", False):
                    self._clear_inline_prompt_display()
                self._set_runtime_busy(False)
                self._active_run = None
                self._set_pending_input_request(None)
                self._set_runtime_status("failed")
                self._set_main_input_placeholder()
                self._write_error(str(event.get("error") or "Request failed."))
            return False
        if event_type == "run_cancelled":
            with self._batch_engine_ui_update():
                self._textual_debugger_active = False
                self._textual_debugger_last_pause_key = None
                self._debugger_inline_breakpoint_visible = False
                if self._runtime_state.pending_input_request is not None and not getattr(self, "_inline_prompt_resolved", False):
                    self._clear_inline_prompt_display()
                self._set_runtime_busy(False)
                self._active_run = None
                self._set_pending_input_request(None)
                self._set_runtime_status("idle")
                self._set_main_input_placeholder()
            return False
        if event_type in {"run_started", "agent_turn_started", "llm_call_started", "tool_started", "handoff"}:
            self._set_runtime_status("running")
        if event_type == "run_cancel_requested":
            self._set_runtime_status("stopping")
        return True

    def _format_runtime_event(self, event: Dict[str, Any]) -> str:
        return format_runtime_event(event)

    def _show_picker(
        self,
        *,
        title: str,
        options: Iterable[PickerOption],
        current_value: str | None,
        on_select: Callable[[str], None],
        help_text: str = "Use arrows to move, Enter to select, Esc to close.",
        empty_message: str = "No matching options.",
    ) -> None:
        option_list = tuple(options)
        if not option_list:
            self._write_error(f"No options available for {title.lower()}.")
            return
        self._present_asset_picker_modal(
            title=title,
            options=option_list,
            current_value=current_value,
            on_select=on_select,
            help_text=help_text,
            empty_message=empty_message,
        )
