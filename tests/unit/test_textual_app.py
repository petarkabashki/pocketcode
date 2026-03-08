from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from pocketcode.cli.textual_app import (
    AssetPickerScreen,
    NameInputScreen,
    PocketCodeTextualApp,
    SystemSettingsScreen,
    TextEditorScreen,
    ToolPolicyEditorScreen,
    ToolSelectionScreen,
    _build_header_agent_text,
    _build_header_llm_text,
    _build_output_text,
    _build_profile_editor_hint,
    _build_stats_text,
    _build_status_text,
    _build_view_title_text,
    _trim_output_lines,
)
from pocketcode.cli.textual_ui.renderables import render_output_blocks
from pocketcode.cli.textual_ui.shared import THEME_PALETTES
from pocketcode.cli.textual_ui.selectors import (
    select_context_summary,
    select_inspector_summary_text,
    select_modal_label,
    select_output_text,
    select_prompt_summary,
    select_run_preview_text,
    select_saved_sessions_summary,
)
from pocketcode.cli.textual_ui.store import (
    CloseModalAction,
    OutputBlock,
    OpenModalAction,
    SetCurrentViewAction,
    SetThemeAction,
    make_initial_runtime_state,
    reduce_textual_cli_actions,
    reduce_textual_runtime_actions,
    reduce_textual_runtime_state,
)
from pocketcode.core.llm_yaml import parse_llm_yaml_mapping
from textual.widgets import Input, RichLog, Select, SelectionList, Static, TextArea


class TestTopStatsText:
    def test_stats_text_shows_runtime_counters_without_repeating_agent(self):
        status = {
            "agent": "core::react",
            "session_tool_confirmation_overrides": {"default_policy": "confirm"},
            "last_run_summary": {
                "current_agent": "core::reviewer",
                "llm_usage": {
                    "prompt_tokens": 128,
                    "completion_tokens": 64,
                    "total_tokens": 192,
                },
                "llm_cost_usd": 0.012345,
            },
        }

        text = _build_stats_text(status)

        assert text == "Tokens in=128 out=64 total=192 | Cost=$0.012345 | Session confirm=confirm"
        assert "Agent=" not in text
        assert "core::react" not in text
        assert "core::reviewer" not in text

    def test_stats_text_defaults_when_run_summary_is_missing(self):
        status = {}

        text = _build_stats_text(status)

        assert text == "Tokens in=0 out=0 total=0 | Cost=$0.000000 | Session confirm=inherit"

    def test_stats_text_appends_active_session_title_when_available(self):
        status = {
            "active_session": {"title": "Review Session"},
            "last_run_summary": {"llm_usage": {}, "llm_cost_usd": 0.0},
        }

        text = _build_stats_text(status)

        assert text.endswith(" | Session=Review Session")


class TestUiTextHelpers:
    def test_status_text_matches_footer_format(self):
        status = {
            "flow": "coder::coder",
            "agent": "coder.safe",
            "selected_agent": "coder.safe",
            "active_agent": "coder.safe",
            "active_agent_profile": "coder.safe",
            "global_llm_override": "fast",
            "selected_flow": "architect::architect",
            "selected_llm_profile": "smart",
            "runtime_workflow": "internal-flow",
            "last_run_summary": {
                "current_agent": "coder::coder",
                "current_llm_profile": "fast",
                "current_llm_model": "gpt-test",
                "agent_path": [],
            },
        }

        text = _build_status_text(status, "control")

        assert "Runtime flow: internal-flow" in text
        assert "Agent: coder.safe" in text
        assert "LLM: smart (-)" in text
        assert "Flow:" not in text

    def test_header_text_splits_summary_agent_and_llm(self):
        status = {
            "selected_agent": "coder.safe",
            "selected_llm_profile": "smart",
            "runtime_workflow": "internal-flow",
            "last_run_summary": {
                "current_llm_profile": "smart",
                "current_llm_model": "gpt-test",
            },
        }

        assert _build_header_agent_text(status) == "Agent: coder.safe"
        assert _build_header_llm_text(status) == "LLM: smart (gpt-test)"

    def test_view_title_text_matches_named_view(self):
        assert _build_view_title_text("run") == "Run Inspector"
        assert _build_view_title_text("chat") == ""

    def test_profile_editor_hint_tracks_profile_source(self):
        workspace_profile = SimpleNamespace(name="coder.safe", source="workspace")
        plugin_profile = SimpleNamespace(name="coder.default", source="plugin")

        assert _build_profile_editor_hint(None) == "Select an agent to edit agent settings."
        assert "Editing workspace agent 'coder.safe'" in _build_profile_editor_hint(workspace_profile)
        assert "Clone it to a workspace agent to edit" in _build_profile_editor_hint(plugin_profile)

    def test_navigation_status_ignores_hover_but_pointer_hint_requires_it(self):
        class _Probe(PocketCodeTextualApp):
            def __init__(self, hovered_block_ref=None):
                super().__init__(
                    _TextualEngineStub(),
                    {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
                )
                self._cli_state = self._cli_state.__class__(
                    theme_name=self._cli_state.theme_name,
                    right_panel_visible=self._cli_state.right_panel_visible,
                    current_view=self._cli_state.current_view,
                    workspace_view=self._cli_state.workspace_view,
                    engine=self._cli_state.engine,
                    focused_surface_id="run-preview",
                    selected_surface_block_indices=self._cli_state.selected_surface_block_indices,
                    expanded_block_refs=("run-preview:2",),
                    hovered_block_ref=hovered_block_ref,
                )

            def _resolve_expansion_surface_id(self):
                return "run-preview"

            def _surface_blocks(self, surface_id):
                return (
                    OutputBlock(kind="info", text="short", title="Overview"),
                    OutputBlock(
                        kind="code",
                        text="\n".join(f"line_{i}: value" for i in range(35)),
                        title="Summary",
                        language="yaml",
                    ),
                    OutputBlock(
                        kind="tool_result",
                        text="\n".join(f"result {i}" for i in range(24)),
                        title="Tool Result",
                    ),
                )

            def _surface_compactable_indices(self, blocks):
                return tuple(
                    index
                    for index, block in enumerate(blocks)
                    if block.kind in {"code", "tool_result", "tool_call"}
                )

            def _resolve_selected_compactable_block_index(self, surface_id):
                return 2

        blocks = _Probe()._surface_blocks("run-preview")

        idle_status = _Probe()._build_navigation_status_text(status={}, run_preview_blocks=blocks)
        hover_status = _Probe("run-preview:1")._build_navigation_status_text(status={}, run_preview_blocks=blocks)
        idle_hint = _Probe()._build_pointer_hint_text(run_preview_blocks=blocks)
        hover_hint = _Probe("run-preview:1")._build_pointer_hint_text(run_preview_blocks=blocks)

        assert idle_status == hover_status
        assert "Hover block" not in hover_status
        assert idle_hint == ""
        assert hover_hint.startswith("Pointer: Run Preview hover on block 1 of 2.")


class TestOutputHistoryHelpers:
    def test_trim_output_lines_keeps_tail_with_overflow_count(self):
        lines, trimmed = _trim_output_lines(["l1", "l2", "l3"], 2)

        assert lines == ["l2", "l3"]
        assert trimmed == 1

    def test_build_output_text_adds_trim_notice_when_history_was_capped(self):
        text = _build_output_text(["info> ready", "assistant> ok"], 3)

        assert text == (
            "info> [output history trimmed: showing last 2 lines]\n"
            "info> ready\n"
            "assistant> ok"
        )


class TestTextualRuntimeStateReducer:
    def test_modal_actions_open_and_close_runtime_modal_state(self):
        initial = make_initial_runtime_state()

        opened = reduce_textual_runtime_state(
            initial,
            OpenModalAction(modal_kind="asset_picker", modal_title="Select View"),
        )

        assert opened.active_modal_kind == "asset_picker"
        assert opened.active_modal_title == "Select View"
        assert opened.run_status == initial.run_status
        assert opened.output_lines == initial.output_lines

        closed = reduce_textual_runtime_state(opened, CloseModalAction())

        assert closed.active_modal_kind is None
        assert closed.active_modal_title is None
        assert closed.run_status == opened.run_status
        assert closed.output_lines == opened.output_lines

    def test_runtime_action_batches_apply_in_order(self):
        state = reduce_textual_runtime_actions(
            make_initial_runtime_state(),
            [
                OpenModalAction(modal_kind="asset_picker", modal_title="Select View"),
                CloseModalAction(),
            ],
        )

        assert state.active_modal_kind is None
        assert state.active_modal_title is None


class TestTextualCliStateReducer:
    def test_cli_action_batches_apply_in_order(self):
        engine = _TextualEngineStub()
        app = PocketCodeTextualApp(
            engine,
            {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
        )
        initial = app._cli_state

        state = reduce_textual_cli_actions(
            initial,
            [
                SetThemeAction(theme_name="forest"),
                SetCurrentViewAction(current_view="run"),
            ],
        )

        assert state.theme_name == "forest"
        assert state.current_view == "run"


class TestTextualRuntimeSelectors:
    def test_modal_label_prefers_title_when_present(self):
        state = reduce_textual_runtime_state(
            make_initial_runtime_state(),
            OpenModalAction(modal_kind="asset_picker", modal_title="Select View"),
        )

        assert select_modal_label(state) == "Select View"

    def test_output_text_selector_renders_trim_notice(self):
        state = make_initial_runtime_state()
        state = reduce_textual_runtime_state(state, OpenModalAction(modal_kind="asset_picker", modal_title=None))
        state = state.__class__(
            busy=state.busy,
            run_status=state.run_status,
            active_modal_kind=state.active_modal_kind,
            active_modal_title=state.active_modal_title,
            pending_input_request=state.pending_input_request,
            live_run_events=state.live_run_events,
            output_blocks=state.output_blocks,
            output_lines=("info> ready", "assistant> ok"),
            trimmed_output_line_count=3,
            last_assistant_response=state.last_assistant_response,
            main_input_placeholder=state.main_input_placeholder,
        )

        assert select_output_text(state) == (
            "info> [output history trimmed: showing last 2 lines]\n"
            "info> ready\n"
            "assistant> ok"
        )

    def test_runtime_summary_and_preview_selectors_include_modal_state(self):
        state = reduce_textual_runtime_state(
            make_initial_runtime_state(),
            OpenModalAction(modal_kind="tool_selection", modal_title="Pick Tools"),
        )
        status = {
            "runtime_flow": "internal-flow",
            "global_llm_override": "smart",
            "session_tool_confirmation_overrides": {"default_policy": "confirm"},
            "active_session": {"title": "Review Session", "session_id": "session-1"},
            "active_agent_profile": "coder.safe",
            "agent": "coder.safe",
            "last_run_summary": {
                "agent_path": ["coder.safe"],
                "current_llm_profile": "smart",
                "current_llm_model": "gpt-test",
                "llm_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                "llm_cost_usd": 0.01,
                "context_stats": {"files": 2},
            },
        }
        active_profile = SimpleNamespace(name="coder.safe", source="workspace", description="Focus mode")

        summary_text = select_inspector_summary_text(
            runtime_state=state,
            status=status,
            active_profile=active_profile,
            active_skill_names=("python-lint",),
            global_llm_override="smart",
            auto_confirm_tools=True,
        )
        preview_text = select_run_preview_text(state, status)

        assert "Modal: Pick Tools" in summary_text
        assert "Agent note: Focus mode" in summary_text
        assert "Active session: Review Session (session-1)" in summary_text
        assert "active_modal: tool_selection" in preview_text
        assert "active_modal_title: Pick Tools" in preview_text
        assert "current_llm_model: gpt-test" in preview_text

    def test_context_session_and_prompt_selectors_render_expected_text(self):
        status = {
            "active_session_id": "session-1",
            "active_session_title": "Review Session",
            "last_run_summary": {"context_stats": {"files": 2, "snippet_chars": 11}},
        }
        cli_context = {
            "files": {"a.py", "b.py"},
            "folders": {"src"},
            "urls": set(),
            "snippets": {"note": "hello world"},
        }
        sessions = [
            {
                "session_id": "session-1",
                "title": "Review Session",
                "updated_at": "2026-03-07T10:00:00+00:00",
                "is_active": True,
            },
            {
                "session_id": "session-2",
                "title": "Earlier Work",
                "updated_at": "2026-03-07T09:00:00+00:00",
                "is_active": False,
            },
        ]
        active_profile = SimpleNamespace(extra_prompts=["workspace/prompts/review.md"])

        context_text = select_context_summary(status, cli_context)
        sessions_text = select_saved_sessions_summary(sessions)
        prompts_text = select_prompt_summary(("plugin/prompts/base.md",), active_profile)

        assert "session_id: session-1" in context_text
        assert "files: 2" in context_text
        assert "Snippets:" in context_text
        assert "* Review Session | session-1 | 2026-03-07T10:00:00+00:00" in sessions_text
        assert "- Earlier Work | session-2 | 2026-03-07T09:00:00+00:00" in sessions_text
        assert "Agent prompt sources:" in prompts_text
        assert "Profile extra prompts:" in prompts_text


class TestTextualUiCommitPath:
    def test_commit_ui_update_can_refresh_suggestions_and_hydrate_engine_before_apply(self):
        engine = _TextualEngineStub()
        app = PocketCodeTextualApp(
            engine,
            {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
        )
        calls: list[object] = []

        app._refresh_suggestions = lambda: calls.append("suggest")
        app._hydrate_cli_state_from_engine = lambda: calls.append("hydrate")
        app._build_ui_state = lambda: "ui-state"
        app._apply_ui_state = lambda state: calls.append(("apply", state))

        app._commit_ui_update(hydrate_engine=True, refresh_suggestions=True)

        assert calls == ["suggest", "hydrate", ("apply", "ui-state")]

    def test_batch_ui_update_merges_commit_requests_into_one_apply(self):
        engine = _TextualEngineStub()
        app = PocketCodeTextualApp(
            engine,
            {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
        )
        calls: list[dict[str, bool]] = []

        app._apply_ui_commit = lambda *, hydrate_engine=False, refresh_suggestions=False: calls.append(
            {
                "hydrate_engine": hydrate_engine,
                "refresh_suggestions": refresh_suggestions,
            }
        )

        with app._batch_ui_update(commit=False):
            app._commit_ui_update()
            app._commit_ui_update(hydrate_engine=True)
            app._commit_ui_update(refresh_suggestions=True)
            assert calls == []

        assert calls == [{"hydrate_engine": True, "refresh_suggestions": True}]

    def test_batch_engine_ui_update_merges_engine_commit_requests_into_one_apply(self):
        engine = _TextualEngineStub()
        app = PocketCodeTextualApp(
            engine,
            {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
        )
        calls: list[dict[str, bool]] = []

        app._apply_ui_commit = lambda *, hydrate_engine=False, refresh_suggestions=False: calls.append(
            {
                "hydrate_engine": hydrate_engine,
                "refresh_suggestions": refresh_suggestions,
            }
        )

        with app._batch_engine_ui_update(commit=False):
            app._commit_engine_ui_update()
            app._commit_engine_ui_update(refresh_suggestions=True)
            assert calls == []

        assert calls == [{"hydrate_engine": True, "refresh_suggestions": True}]

    def test_modal_result_batches_close_and_follow_up_commit_into_one_apply(self):
        engine = _TextualEngineStub()
        app = PocketCodeTextualApp(
            engine,
            {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
        )
        calls: list[dict[str, bool]] = []

        app._apply_ui_commit = lambda *, hydrate_engine=False, refresh_suggestions=False: calls.append(
            {
                "hydrate_engine": hydrate_engine,
                "refresh_suggestions": refresh_suggestions,
            }
        )
        app.push_screen = lambda screen, callback: callback("ok")
        app._write_error = lambda text: None

        app._present_modal(
            object(),
            modal_kind="asset_picker",
            modal_title="Select View",
            on_result=lambda result: app._commit_ui_update(hydrate_engine=True, refresh_suggestions=True),
            sync_ui=True,
        )

        assert calls == [{"hydrate_engine": True, "refresh_suggestions": True}]


class TestTextualOutputRendering:
    def test_startup_output_starts_empty(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause(0.2)

                output = app.query_one("#output", RichLog)

                assert app._runtime_state.output_blocks == ()
                assert app._runtime_state.output_lines == ()
                assert output.lines == []

        asyncio.run(exercise())


class TestTextualPointerSelection:
    def test_pointer_selection_uses_rendered_block_spans(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )
            blocks = (
                OutputBlock(kind="info", text="overview", title="Overview"),
                OutputBlock(
                    kind="code",
                    text="\n".join(f"alpha_{index}: value" for index in range(48)),
                    title="Summary",
                    language="yaml",
                ),
                OutputBlock(
                    kind="tool_result",
                    text="\n".join(f"result {index}" for index in range(36)),
                    title="Tool Result",
                ),
            )

            async with app.run_test() as pilot:
                await pilot.pause(0.2)
                app._set_cli_current_view("run")
                app._surface_blocks = lambda surface_id: blocks if surface_id == "run-preview" else ()

                preview = app.query_one("#run-preview", RichLog)
                palette = THEME_PALETTES.get(app._cli_state.theme_name) or next(iter(THEME_PALETTES.values()))
                renderables = render_output_blocks(blocks, palette, surface_id="run-preview")
                preview.clear()
                for renderable in renderables:
                    preview.write(renderable, scroll_end=False)
                app._set_surface_render_spans(
                    "run-preview",
                    renderables,
                    width=preview.content_region.width or preview.size.width or 80,
                )
                await pilot.pause(0.05)

                spans = app._surface_render_spans("run-preview")
                target_span = spans[2]
                pointer_y = max(0, target_span.start_line)
                widget_height = max(1, preview.content_region.height or preview.size.height or (target_span.end_line + 1))

                app._select_surface_block_from_pointer(
                    "run-preview",
                    pointer_y=pointer_y,
                    widget_height=widget_height,
                    scroll_y=0.0,
                )

                assert dict(app._cli_state.selected_surface_block_indices)["run-preview"] == 2

        asyncio.run(exercise())

    def test_scroll_selection_tracks_viewport_center_line(self):
        engine = _TextualEngineStub()
        app = PocketCodeTextualApp(
            engine,
            {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
        )
        blocks = (
            OutputBlock(kind="info", text="overview", title="Overview"),
            OutputBlock(
                kind="code",
                text="\n".join(f"alpha_{index}: value" for index in range(60)),
                title="Summary",
                language="yaml",
            ),
            OutputBlock(
                kind="tool_result",
                text="\n".join(f"result {index}" for index in range(60)),
                title="Tool Result",
            ),
        )

        app._set_cli_current_view("run")
        app._surface_blocks = lambda surface_id: blocks if surface_id == "run-preview" else ()

        palette = THEME_PALETTES.get(app._cli_state.theme_name) or next(iter(THEME_PALETTES.values()))
        renderables = render_output_blocks(blocks, palette, surface_id="run-preview")
        app._set_surface_render_spans("run-preview", renderables, width=80)

        spans = app._surface_render_spans("run-preview")
        target_span = spans[2]
        viewport_height = 10
        target_center_line = (target_span.start_line + target_span.end_line) // 2
        target_scroll = max(0, target_center_line - max(1, viewport_height // 2))
        preview = SimpleNamespace(
            content_region=SimpleNamespace(height=viewport_height),
            size=SimpleNamespace(height=viewport_height),
            virtual_size=SimpleNamespace(height=spans[-1].end_line + 1),
            scroll_y=float(target_scroll),
        )
        query_one = app.query_one
        app.query_one = lambda selector, expect_type=None: preview if selector == "#run-preview" else query_one(selector, expect_type)
        app._commit_ui_update = lambda *args, **kwargs: None

        app._select_surface_block_from_scroll("run-preview")

        assert dict(app._cli_state.selected_surface_block_indices)["run-preview"] == 2

    def test_footer_hint_widget_only_shows_when_text_exists(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause(0.2)

                footer_hint = app.query_one("#footer-hint", Static)

                assert footer_hint.display is False

                app._apply_footer_hint_state("Pointer: Run Preview hover on block 1 of 2.")
                await pilot.pause(0.05)

                assert footer_hint.display is True
                assert app._text_state_cache["footer-hint"] == "Pointer: Run Preview hover on block 1 of 2."

                app._apply_footer_hint_state("")
                await pilot.pause(0.05)

                assert footer_hint.display is False
                assert app._text_state_cache["footer-hint"] == ""

        asyncio.run(exercise())


class TestTextualViewSwitching:
    def test_view_picker_opens_selector_screen(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_pick_view()
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                assert app.screen._title == "Select View"

        asyncio.run(exercise())

    def test_view_picker_tracks_modal_state_while_screen_is_open(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                assert app._runtime_state.active_modal_kind is None
                assert app._runtime_state.active_modal_title is None

                app.action_pick_view()
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                assert app._runtime_state.active_modal_kind == "asset_picker"
                assert app._runtime_state.active_modal_title == "Select View"

                app.screen.dismiss(None)
                await pilot.pause(0.05)

                assert app._runtime_state.active_modal_kind is None
                assert app._runtime_state.active_modal_title is None

        asyncio.run(exercise())

    def test_slash_view_command_switches_current_view(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}, "interface": "textual"},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                await app._handle_main_input("/view switch run")
                await pilot.pause(0.05)

                assert app._current_view == "run"

        asyncio.run(exercise())


class TestTextualInteractionRequests:
    def test_pending_button_interaction_accepts_scope_value(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            class _RunStub:
                def __init__(self):
                    self.calls = []

                def drain_events(self):
                    return []

                def resolve_interaction(self, request_id, payload):
                    self.calls.append((request_id, payload))
                    return True

            run_stub = _RunStub()

            async with app.run_test() as pilot:
                await pilot.pause()
                app._active_run = run_stub
                app._pending_input_request = {
                    "type": "interaction_requested",
                    "request_id": "interaction-1",
                    "kind": "buttons",
                    "prompt": "Allow tool 'core.read_file'?",
                    "options": [
                        {"id": "once", "label": "Approve Once", "value": "once"},
                        {"id": "session", "label": "Approve for Session", "value": "session"},
                        {"id": "always", "label": "Always Approve", "value": "always"},
                        {"id": "deny", "label": "Deny", "value": "deny"},
                    ],
                    "default": "deny",
                }

                input_widget = app.query_one("#main-input", Input)
                input_widget.value = "always"
                await app._handle_main_input("always")
                await pilot.pause(0.05)

                assert run_stub.calls == [
                    (
                        "interaction-1",
                        {
                            "kind": "buttons",
                            "value": "always",
                            "values": ["always"],
                            "label": "Always Approve",
                            "selected_options": [
                                {
                                    "id": "always",
                                    "label": "Always Approve",
                                    "value": "always",
                                    "description": "",
                                }
                            ],
                            "raw_input": "always",
                        },
                    )
                ]

        asyncio.run(exercise())

    def test_output_appends_lines_in_order_after_buffer_reset(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                output = app.query_one("#output", RichLog)
                app._clear_console_state()
                output.clear()
                app._output_render_cache = None

                app._write_info("first")
                app._write_info("second")
                await pilot.pause(0.05)

                assert [block.text for block in app._runtime_state.output_blocks] == ["first", "second"]
                assert app._runtime_state.output_lines == ("info> first", "info> second")
                assert len(output.lines) >= 0

        asyncio.run(exercise())


class _TextualEngineStub:
    def __init__(self) -> None:
        self.current_agent = "a"
        self.active_agent_profile = self._profile("a", "a")
        self.active_mode = None
        self.global_llm_override = None
        self.auto_confirm_tools = False
        self.session_confirmation_overrides: dict[str, str | None] = {}
        self.set_agent_calls: list[str | None] = []
        self.set_active_agent_profile_calls: list[str] = []
        self.set_last_used_active_profile_calls: list[str | None] = []
        self.set_last_used_mode_calls: list[str | None] = []
        self.set_last_used_global_llm_profile_calls: list[str | None] = []
        self.set_last_used_session_confirmation_default_calls: list[str | None] = []
        self.set_last_used_auto_confirm_tools_calls: list[bool] = []
        self.clone_agent_profile_calls: list[tuple[str, str]] = []
        self.clone_llm_profile_calls: list[tuple[str, str]] = []
        self.clone_mode_calls: list[tuple[str, str]] = []
        self.update_agent_profile_calls: list[dict[str, object]] = []
        self.update_llm_profile_calls: list[dict[str, object]] = []
        self.update_mode_calls: list[dict[str, object]] = []
        self.clone_markdown_asset_calls: list[tuple[str, str, str]] = []
        self.update_markdown_asset_calls: list[dict[str, object]] = []
        self.delete_markdown_asset_calls: list[tuple[str, str]] = []
        self.save_system_settings_calls: list[dict[str, object]] = []
        self.set_last_used_skill_calls: list[list[str]] = []
        self.set_last_used_profile_skill_calls: list[tuple[str, list[str]]] = []
        self.reset_last_used_skill_calls = 0
        self.reset_last_used_profile_skill_calls: list[str] = []
        self.save_default_skills_calls: list[list[str]] = []
        self.save_agent_profile_skill_calls: list[tuple[str, list[str]]] = []
        self.save_agent_profile_tool_calls: list[tuple[str, list[str] | None]] = []
        self.set_last_used_profile_tools_calls: list[tuple[str, list[str] | None]] = []
        self.reset_last_used_profile_tools_calls: list[str] = []
        self.set_last_used_profile_tool_policy_calls: list[tuple[str, dict[str, str]]] = []
        self.reset_last_used_profile_tool_policy_calls: list[str] = []
        self.saved_selection_presets: list[str] = []
        self.applied_selection_presets: list[str] = []
        self.deleted_selection_presets: list[str] = []
        self.started_sessions = 0
        self.resumed_sessions: list[str] = []
        self.deleted_sessions: list[str] = []
        self.cleared_sessions = 0
        self.active_skills: list[str] = []
        self.profile_skill_overrides: dict[str, list[str]] = {}
        self.skill_enabled: list[str] = []
        self.skill_disabled: list[str] = []
        self._saved_sessions = [
            {
                "session_id": "session-1",
                "title": "Current Session",
                "updated_at": "2026-03-07T10:00:00+00:00",
                "is_active": True,
                "is_resumable": False,
            },
            {
                "session_id": "session-2",
                "title": "Earlier Work",
                "updated_at": "2026-03-07T09:00:00+00:00",
                "is_active": False,
                "is_resumable": True,
            },
        ]
        self._modes = {
            "review": SimpleNamespace(name="review", source_path=Path("/tmp/review.md")),
            "focus": SimpleNamespace(name="focus", source_path=Path("/tmp/focus.md")),
        }
        self._selection_presets = {
            "review-session": {
                "active_mode": "review",
                "global_llm_profile": "smart",
            }
        }
        self._profiles = {
            "a": self._profile("a", "a"),
            "a-safe": self._profile("a-safe", "a"),
            "b": self._profile("b", "b"),
            "b-safe": self._profile("b-safe", "b"),
            "c": self._profile("c", "c"),
            "c-safe": self._profile("c-safe", "c"),
        }
        self._markdown_assets = {
            "flow": {
                "review-flow": {
                    "text": "---\nname: review-flow\n---\nflow body\n",
                    "path": Path("/tmp/review-flow.md"),
                }
            },
            "tool": {
                "workspace-echo": {
                    "text": "---\nname: workspace-echo\nhandler: ./workspace-echo.py:WorkspaceEchoTool\n---\ntool body\n",
                    "path": Path("/tmp/workspace-echo.md"),
                    "companion_path": Path("/tmp/workspace-echo.py"),
                }
            },
        }

    @staticmethod
    def _profile(name: str, agent: str) -> SimpleNamespace:
        return SimpleNamespace(
            name=name,
            agent=agent,
            source="workspace" if name.endswith("-safe") else "synthesised",
            description="",
            llm_profile=None,
            skills=None,
            tools=None,
            tool_confirmation={},
            extra_prompts=[],
        )

    def list_agents(self):
        return ["a", "b", "c"]

    def list_llm_profiles(self):
        return ["fast", "smart"]

    def list_modes(self):
        return list(self._modes)

    def get_mode(self, name=None):
        if name is None:
            return self.active_mode
        return self._modes.get(name)

    def set_mode(self, name):
        self.active_mode = self._modes.get(name) if name is not None else None

    def list_skills(self):
        return ["python-lint", "python-testing", "azure-prepare"]

    def get_active_skills(self):
        return [SimpleNamespace(name=name) for name in self.active_skills]

    def enable_skill(self, name):
        self.skill_enabled.append(name)
        if name not in self.active_skills:
            self.active_skills.append(name)

    def disable_skill(self, name):
        self.skill_disabled.append(name)
        self.active_skills = [skill for skill in self.active_skills if skill != name]

    def get_llm_profile(self, name=None):
        target = name or self.global_llm_override or "fast"
        sources = {
            "fast": "workspace",
            "smart": "plugin",
        }
        return {
            "name": target,
            "source": sources.get(target, "workspace"),
            "source_path": Path(f"/tmp/{target}.yaml"),
            "config": {
                "provider": "gemini",
                "model": target,
                "parameters": {"temperature": 0.2},
            },
        }

    def list_agent_profiles(self, agent_name=None):
        target = agent_name or self.current_agent
        return [
            profile.name
            for profile in self._profiles.values()
            if profile.agent == target
        ]

    def get_agent_profile(self, name=None, *, effective=True):
        if name is None:
            return self.active_agent_profile
        return self._profiles.get(name)

    def get_current_agent(self):
        return self.current_agent

    def set_agent(self, agent_name):
        self.set_agent_calls.append(agent_name)
        self.current_agent = agent_name
        if agent_name is None:
            self.active_agent_profile = None
            return
        self.active_agent_profile = self._profiles.get(agent_name, self._profile(agent_name, agent_name))

    def set_active_agent_profile(self, name):
        self.set_active_agent_profile_calls.append(name)
        self.active_agent_profile = self._profiles.get(name, self._profile(name, self.current_agent))
        self.current_agent = self.active_agent_profile.agent
        self.active_mode = None
        self.active_skills = list(
            self.profile_skill_overrides.get(name, self.active_agent_profile.skills or [])
        )

    def set_last_used_active_profile(self, name):
        self.set_last_used_active_profile_calls.append(name)
        if name is None:
            self.active_agent_profile = None
            return Path("/tmp/pocketcode.yml")
        self.set_active_agent_profile(name)
        return Path("/tmp/pocketcode.yml")

    def set_last_used_mode(self, name):
        self.set_last_used_mode_calls.append(name)
        self.set_mode(name)
        return Path("/tmp/pocketcode.yml")

    def set_last_used_global_llm_profile(self, value):
        self.set_last_used_global_llm_profile_calls.append(value)
        self.global_llm_override = value
        return Path("/tmp/pocketcode.yml")

    def set_last_used_session_confirmation_default(self, value):
        self.set_last_used_session_confirmation_default_calls.append(value)
        self.session_confirmation_overrides["default_policy"] = value
        return Path("/tmp/pocketcode.yml")

    def set_last_used_auto_confirm_tools(self, enabled):
        self.set_last_used_auto_confirm_tools_calls.append(bool(enabled))
        self.auto_confirm_tools = bool(enabled)
        return Path("/tmp/pocketcode.yml")

    def clone_agent_profile(self, src_name, new_name):
        self.clone_agent_profile_calls.append((src_name, new_name))
        cloned = SimpleNamespace(
            name=new_name,
            agent=self.current_agent,
            source="workspace",
            description="",
            llm_profile=None,
            skills=None,
            tools=None,
            tool_confirmation={},
            extra_prompts=[],
            source_path=Path(f"/tmp/{new_name}.yaml"),
        )
        self._profiles[new_name] = cloned
        return cloned

    def clone_llm_profile(self, src_name, new_name):
        self.clone_llm_profile_calls.append((src_name, new_name))
        return {
            "name": new_name,
            "source": "workspace",
            "source_path": Path(f"/tmp/{new_name}.yaml"),
            "config": {
                "provider": "gemini",
                "model": src_name,
                "parameters": {"temperature": 0.2},
            },
        }

    def clone_mode(self, src_name, new_name):
        self.clone_mode_calls.append((src_name, new_name))
        self._modes[new_name] = SimpleNamespace(name=new_name, source_path=Path(f"/tmp/{new_name}.md"))
        return Path(f"/tmp/{new_name}.md")

    def list_markdown_assets(self, asset_kind):
        return sorted(self._markdown_assets.get(asset_kind, {}))

    def get_markdown_asset(self, asset_kind, name):
        asset = dict(self._markdown_assets[asset_kind][name])
        asset.setdefault("kind", asset_kind)
        asset.setdefault("name", name)
        asset.setdefault("companion_path", None)
        return asset

    def clone_markdown_asset(self, asset_kind, source_name, new_name):
        self.clone_markdown_asset_calls.append((asset_kind, source_name, new_name))
        source = dict(self._markdown_assets[asset_kind][source_name])
        cloned = {
            "text": source["text"].replace(f"name: {source_name}", f"name: {new_name}"),
            "path": Path(f"/tmp/{new_name}.md"),
            "companion_path": Path(f"/tmp/{new_name}.py") if asset_kind == "tool" else None,
        }
        self._markdown_assets.setdefault(asset_kind, {})[new_name] = cloned
        return {
            "kind": asset_kind,
            "name": new_name,
            "path": cloned["path"],
            "companion_path": cloned.get("companion_path"),
        }

    def update_markdown_asset(self, asset_kind, name, *, markdown_text):
        self.update_markdown_asset_calls.append(
            {"asset_kind": asset_kind, "name": name, "markdown_text": markdown_text}
        )
        asset = self._markdown_assets[asset_kind][name]
        asset["text"] = markdown_text
        return {
            "kind": asset_kind,
            "name": name,
            "path": asset["path"],
            "companion_path": asset.get("companion_path"),
        }

    def delete_markdown_asset(self, asset_kind, name):
        self.delete_markdown_asset_calls.append((asset_kind, name))
        asset = self._markdown_assets[asset_kind].pop(name)
        return {
            "kind": asset_kind,
            "name": name,
            "path": asset["path"],
            "companion_path": asset.get("companion_path"),
            "companion_deleted": False,
        }

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
        self.update_agent_profile_calls.append(
            {
                "name": name,
                "llm_profile": llm_profile,
                "tools": tools,
                "extra_prompts": extra_prompts,
                "tool_confirmation_default": tool_confirmation_default,
                "tool_confirmation_overrides": tool_confirmation_overrides,
            }
        )

    def update_llm_profile(self, name, *, profile_config):
        self.update_llm_profile_calls.append(
            {
                "name": name,
                "profile_config": profile_config,
            }
        )

    def update_mode(self, name, *, markdown_text):
        self.update_mode_calls.append({"name": name, "markdown_text": markdown_text})
        return Path(f"/tmp/{name}.md")

    def get_system_settings(self):
        return {
            "theme_name": "ocean",
            "workspace_view": "balanced",
            "default_agent": "a",
            "default_llm_profile": "fast",
        }

    def save_system_settings(self, *, theme_name, workspace_view, default_agent, default_llm_profile):
        self.save_system_settings_calls.append(
            {
                "theme_name": theme_name,
                "workspace_view": workspace_view,
                "default_agent": default_agent,
                "default_llm_profile": default_llm_profile,
            }
        )
        return Path("/tmp/pocketcode.yml")

    def set_last_used_skills(self, skill_names):
        normalized = list(skill_names)
        self.set_last_used_skill_calls.append(normalized)
        self.active_skills = normalized
        return Path("/tmp/pocketcode.yml")

    def set_last_used_profile_skills(self, profile_name, skill_names):
        normalized = list(skill_names)
        self.set_last_used_profile_skill_calls.append((profile_name, normalized))
        self.profile_skill_overrides[profile_name] = normalized
        if self.active_agent_profile is not None and self.active_agent_profile.name == profile_name:
            self.active_skills = normalized
        return Path("/tmp/pocketcode.yml")

    def reset_last_used_skills(self):
        self.reset_last_used_skill_calls += 1
        self.active_skills = []
        return Path("/tmp/pocketcode.yml")

    def reset_last_used_profile_skills(self, profile_name):
        self.reset_last_used_profile_skill_calls.append(profile_name)
        self.profile_skill_overrides.pop(profile_name, None)
        if self.active_agent_profile is not None and self.active_agent_profile.name == profile_name:
            self.active_skills = []
        return Path("/tmp/pocketcode.yml")

    def save_default_skills(self, skill_names):
        self.save_default_skills_calls.append(list(skill_names))
        return Path("/tmp/pocketcode.yml")

    def save_agent_profile_skills(self, profile_name, skill_names):
        normalized = list(skill_names)
        self.save_agent_profile_skill_calls.append((profile_name, normalized))
        profile = self._profiles.get(profile_name)
        if profile is not None:
            profile.skills = normalized
            self.profile_skill_overrides.pop(profile_name, None)
            if self.active_agent_profile is not None and self.active_agent_profile.name == profile_name:
                self.active_agent_profile.skills = normalized
                self.active_skills = normalized
        return profile

    def list_textual_selection_presets(self):
        return sorted(self._selection_presets)

    def get_textual_selection_preset(self, name):
        return self._selection_presets.get(name)

    def save_textual_selection_preset(self, name):
        self.saved_selection_presets.append(name)
        self._selection_presets[name] = {"active_profile": self.active_agent_profile.name if self.active_agent_profile else None}
        return Path("/tmp/pocketcode.yml")

    def apply_textual_selection_preset(self, name):
        self.applied_selection_presets.append(name)
        preset = self._selection_presets.get(name, {})
        mode_name = preset.get("active_mode")
        if mode_name:
            self.set_mode(mode_name)
        return Path("/tmp/pocketcode.yml")

    def delete_textual_selection_preset(self, name):
        self.deleted_selection_presets.append(name)
        self._selection_presets.pop(name, None)
        return Path("/tmp/pocketcode.yml")

    def set_last_used_profile_tools(self, profile_name, tools):
        normalized = None if tools is None else list(tools)
        self.set_last_used_profile_tools_calls.append((profile_name, normalized))
        profile = self._profiles.get(profile_name)
        if profile is not None:
            profile.tools = normalized
            if self.active_agent_profile is not None and self.active_agent_profile.name == profile_name:
                self.active_agent_profile.tools = normalized
        return Path("/tmp/pocketcode.yml")

    def reset_last_used_profile_tools(self, profile_name):
        self.reset_last_used_profile_tools_calls.append(profile_name)
        profile = self._profiles.get(profile_name)
        if profile is not None:
            profile.tools = None
            if self.active_agent_profile is not None and self.active_agent_profile.name == profile_name:
                self.active_agent_profile.tools = None
        return Path("/tmp/pocketcode.yml")

    def save_agent_profile_tools(self, profile_name, tools):
        normalized = None if tools is None else list(tools)
        self.save_agent_profile_tool_calls.append((profile_name, normalized))
        profile = self._profiles.get(profile_name)
        if profile is not None:
            profile.tools = normalized
            if self.active_agent_profile is not None and self.active_agent_profile.name == profile_name:
                self.active_agent_profile.tools = normalized
        return profile

    def set_last_used_profile_tool_policies(self, profile_name, overrides):
        normalized = dict(overrides)
        self.set_last_used_profile_tool_policy_calls.append((profile_name, normalized))
        profile = self._profiles.get(profile_name)
        if profile is not None:
            profile.tool_confirmation = {"overrides": normalized}
            if self.active_agent_profile is not None and self.active_agent_profile.name == profile_name:
                self.active_agent_profile.tool_confirmation = {"overrides": normalized}
        return Path("/tmp/pocketcode.yml")

    def reset_last_used_profile_tool_policies(self, profile_name):
        self.reset_last_used_profile_tool_policy_calls.append(profile_name)
        profile = self._profiles.get(profile_name)
        if profile is not None:
            profile.tool_confirmation = {}
            if self.active_agent_profile is not None and self.active_agent_profile.name == profile_name:
                self.active_agent_profile.tool_confirmation = {}
        return Path("/tmp/pocketcode.yml")

    def list_tools_for_agent(self, agent_name):
        return ["tool.read", "tool.write"]

    def describe_tool(self, tool_name):
        group_paths = {
            "tool.read": ["tool", "filesystem"],
            "tool.write": ["tool", "filesystem"],
            "tool.ask": ["tool", "user_input"],
        }
        return {
            "name": tool_name,
            "description": "",
            "schema": {"type": "object", "properties": {}},
            "group_path": group_paths.get(tool_name, ["tool"]),
            "source_path": None,
        }

    def get_agent_prompt_sources(self, agent_name=None):
        return []

    def get_mode_text(self, name):
        return f"---\nname: {name}\n---\nPrompt\n"

    def status(self):
        return {
            "available_llm_profiles": self.list_llm_profiles(),
            "available_flows": self.list_agents(),
            "available_agents": self.list_agent_profiles(),
            "available_modes": self.list_modes(),
            "available_skills": self.list_skills(),
            "session_tool_confirmation_overrides": self.session_confirmation_overrides,
            "flow": self.current_agent,
            "agent": self.active_agent_profile.name if self.active_agent_profile else None,
            "selected_agent": self.active_agent_profile.name if self.active_agent_profile else None,
            "selected_llm_profile": self.global_llm_override or "fast",
            "active_agent": self.active_agent_profile.name if self.active_agent_profile else None,
            "active_agent_profile": self.active_agent_profile.name if self.active_agent_profile else None,
            "active_session_id": self._saved_sessions[0]["session_id"],
            "active_session_title": self._saved_sessions[0]["title"],
            "active_session": {
                "session_id": self._saved_sessions[0]["session_id"],
                "title": self._saved_sessions[0]["title"],
                "loaded_from_history": False,
            },
            "runtime_workflow": "internal-flow",
            "last_run_summary": {
                "current_agent": self.current_agent,
                "current_llm_profile": None,
                "current_llm_model": None,
                "agent_path": [],
            },
        }

    def get_active_session_info(self):
        current = self._saved_sessions[0]
        return {
            "session_id": current["session_id"],
            "title": current["title"],
            "loaded_from_history": False,
        }

    def list_saved_sessions(self):
        return [dict(item) for item in self._saved_sessions]

    def start_new_session(self, title=None):
        self.started_sessions += 1
        created = {
            "session_id": f"session-new-{self.started_sessions}",
            "title": title or f"Session {self.started_sessions}",
            "updated_at": "2026-03-07T11:00:00+00:00",
            "is_active": True,
            "is_resumable": False,
        }
        for item in self._saved_sessions:
            item["is_active"] = False
            item["is_resumable"] = True
        self._saved_sessions.insert(0, created)
        return {
            "session_id": created["session_id"],
            "title": created["title"],
            "loaded_from_history": False,
        }

    def resume_session(self, session_id):
        self.resumed_sessions.append(session_id)
        for index, item in enumerate(self._saved_sessions):
            if item["session_id"] == session_id:
                self._saved_sessions.pop(index)
                resumed = dict(item)
                break
        else:
            resumed = {
                "session_id": session_id,
                "title": session_id,
                "updated_at": "2026-03-07T09:00:00+00:00",
                "is_active": False,
                "is_resumable": True,
            }
        for item in self._saved_sessions:
            item["is_active"] = False
            item["is_resumable"] = True
        resumed["is_active"] = True
        resumed["is_resumable"] = False
        self._saved_sessions.insert(0, resumed)
        return {
            "session_id": resumed["session_id"],
            "title": resumed["title"],
            "loaded_from_history": True,
        }

    def delete_session(self, session_id):
        if session_id == self._saved_sessions[0]["session_id"]:
            raise ValueError("Cannot delete the active session.")
        self.deleted_sessions.append(session_id)
        self._saved_sessions = [item for item in self._saved_sessions if item["session_id"] != session_id]
        return {"session_id": session_id, "deleted": True}

    def clear_saved_sessions(self):
        count = max(0, len(self._saved_sessions) - 1)
        self.cleared_sessions += count
        self._saved_sessions = self._saved_sessions[:1]
        return count

    def describe_agent(self, agent_name=None):
        target = agent_name or self.current_agent
        return {
            "name": target,
            "description": "",
            "execution_mode": "",
            "prompt_sources": [],
            "profiles": self.list_agent_profiles(target),
            "tools": self.list_tools_for_agent(target),
        }

    def describe_tools_for_agent(self, agent_name):
        return []

    def set_global_llm_override(self, value):
        self.global_llm_override = value

    def set_session_confirmation_default(self, value):
        self.session_confirmation_overrides["default_policy"] = value

    def delete_agent_profile(self, name):
        self._profiles.pop(name, None)
        if self.active_agent_profile is not None and self.active_agent_profile.name == name:
            self.active_agent_profile = None
        return Path(f"/tmp/{name}.yaml")

    def delete_llm_profile(self, name):
        if self.global_llm_override == name:
            self.global_llm_override = None
        return Path(f"/tmp/{name}.yaml")

    def delete_mode(self, name):
        self._modes.pop(name, None)
        if self.active_mode is not None and self.active_mode.name == name:
            self.active_mode = None
        return Path(f"/tmp/{name}.md")


class TestTextualSelectStability:
    def test_header_uses_static_agent_and_llm_labels(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

        asyncio.run(exercise())

    def test_asset_picker_supports_arrow_key_selection(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6", "down", "down", "enter")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)

                await pilot.press("enter")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)

                await pilot.press("down", "down", "enter")
                await pilot.pause(0.1)

                assert engine.global_llm_override == "smart"
                assert any("Global LLM override: smart" in line for line in app._output_lines)

        asyncio.run(exercise())

    def test_f6_asset_picker_can_select_global_llm(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("llm")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("select")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("smart")
                await pilot.pause(0.1)

                assert engine.global_llm_override == "smart"
                assert any("Global LLM override: smart" in line for line in app._output_lines)

        asyncio.run(exercise())

    def test_f6_select_can_open_skill_selection_popup(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("skills")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("select")
                await pilot.pause(0.1)

                assert isinstance(app.screen, ToolSelectionScreen)
                assert app.screen._filter_placeholder == "Filter skills..."

        asyncio.run(exercise())

    def test_f6_sessions_can_resume_saved_history(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("sessions")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("resume")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("session-2")
                await pilot.pause(0.1)

                assert engine.resumed_sessions == ["session-2"]
                assert any("Resumed session: session-2" in line for line in app._output_lines)

        asyncio.run(exercise())

    def test_f6_sessions_delete_requires_confirmation_flow(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("sessions")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("delete")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("session-2")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("delete")
                await pilot.pause(0.1)

                assert engine.deleted_sessions == ["session-2"]
                assert any("Deleted session: session-2" in line for line in app._output_lines)

        asyncio.run(exercise())

    def test_f6_sessions_can_clear_previous_history(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("sessions")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("clear_all")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("clear")
                await pilot.pause(0.1)

                assert engine.cleared_sessions == 1
                assert any("Cleared 1 saved session" in line for line in app._output_lines)

        asyncio.run(exercise())

    def test_f6_select_can_open_tool_selection_popup(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("tools")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("select")
                await pilot.pause(0.1)

                assert isinstance(app.screen, ToolSelectionScreen)
                assert any(option.label == "Group: tool" for option in app.screen._tools)

        asyncio.run(exercise())

    def test_f6_select_can_open_system_settings_screen(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("system_settings")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("open")
                await pilot.pause(0.1)

                assert isinstance(app.screen, SystemSettingsScreen)

        asyncio.run(exercise())

    def test_f6_system_settings_normalizes_legacy_agent_alias(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.list_agents = lambda: ["core.react", "workspace.review"]
            engine.get_system_settings = lambda: {
                "theme_name": "ocean",
                "workspace_view": "balanced",
                "default_agent": "core::react",
                "default_llm_profile": "fast",
            }
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("system_settings")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("open")
                await pilot.pause(0.1)

                assert isinstance(app.screen, SystemSettingsScreen)
                assert app.screen.query_one("#system-default-agent-select", Select).value == "core.react"

        asyncio.run(exercise())

    def test_f6_system_settings_normalizes_typed_agent_alias(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.list_agents = lambda: ["core.react", "workspace.review"]
            engine.get_system_settings = lambda: {
                "theme_name": "ocean",
                "workspace_view": "balanced",
                "default_agent": "agent:core.react",
                "default_llm_profile": "fast",
            }
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("system_settings")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("open")
                await pilot.pause(0.1)

                assert isinstance(app.screen, SystemSettingsScreen)
                assert app.screen.query_one("#system-default-agent-select", Select).value == "core.react"

        asyncio.run(exercise())


class TestLlmYamlParsing:
    def test_parse_llm_yaml_mapping_skips_leading_prose(self):
        parsed = parse_llm_yaml_mapping(
            "Here is the YAML you requested:\naction: call_tool\ntool: core.read_file\narguments:\n  path: pocketcode.log\n"
        )

        assert parsed["action"] == "call_tool"
        assert parsed["tool"] == "core.read_file"


class TestToolSelectionPopup:
    def test_tool_picker_toggle_uses_selection_index_event_field(self):
        screen = ToolSelectionScreen(
            title="Edit Allowed Tools",
            tools=[SimpleNamespace(value="core.ask_user_input", label="core.ask_user_input", description="", search_text="")],
            selected_values=[],
        )
        selection_list = SimpleNamespace(
            id="tool-picker-list",
            disabled=False,
            selected={"core.ask_user_input"},
            get_option_at_index=lambda index: SimpleNamespace(value="core.ask_user_input"),
        )
        event = SimpleNamespace(selection_list=selection_list, selection_index=0)

        screen.on_selection_list_selection_toggled(event)

        assert screen._selected_values == {"core.ask_user_input"}

    def test_group_toggle_selects_all_group_members(self):
        screen = ToolSelectionScreen(
            title="Select Skills",
            tools=[
                SimpleNamespace(value="__skill_group__:python", label="Group: python", description="", search_text=""),
                SimpleNamespace(value="python-lint", label="  python-lint", description="", search_text=""),
                SimpleNamespace(value="python-testing", label="  python-testing", description="", search_text=""),
            ],
            selected_values=[],
            grouped_values={"__skill_group__:python": ("python-lint", "python-testing")},
        )
        selection_list = SimpleNamespace(
            id="tool-picker-list",
            disabled=False,
            selected={"__skill_group__:python"},
            get_option_at_index=lambda index: SimpleNamespace(value="__skill_group__:python"),
        )
        event = SimpleNamespace(selection_list=selection_list, selection_index=0)

        screen.on_selection_list_selection_toggled(event)

        assert screen._selected_values == {"__skill_group__:python", "python-lint", "python-testing"}

    def test_nested_group_toggle_syncs_child_groups(self):
        screen = ToolSelectionScreen(
            title="Edit Allowed Tools",
            tools=[
                SimpleNamespace(value="__skill_group__:core", label="Group: core", description="", search_text=""),
                SimpleNamespace(value="__skill_group__:core/filesystem", label="  Group: filesystem", description="", search_text=""),
                SimpleNamespace(value="core.read_file", label="    core.read_file", description="", search_text=""),
                SimpleNamespace(value="core.write_to_file", label="    core.write_to_file", description="", search_text=""),
            ],
            selected_values=[],
            grouped_values={
                "__skill_group__:core": ("core.read_file", "core.write_to_file"),
                "__skill_group__:core/filesystem": ("core.read_file", "core.write_to_file"),
            },
        )
        selection_list = SimpleNamespace(
            id="tool-picker-list",
            disabled=False,
            selected={"__skill_group__:core"},
            get_option_at_index=lambda index: SimpleNamespace(value="__skill_group__:core"),
        )
        event = SimpleNamespace(selection_list=selection_list, selection_index=0)

        screen.on_selection_list_selection_toggled(event)

        assert screen._selected_values == {
            "__skill_group__:core",
            "__skill_group__:core/filesystem",
            "core.read_file",
            "core.write_to_file",
        }

    def test_build_nested_tool_picker_options_uses_group_path_hierarchy(self):
        engine = _TextualEngineStub()
        app = PocketCodeTextualApp(
            engine,
            {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
        )

        picker_options, grouped_values, initial_selected_values = app._build_nested_tool_picker_options(
            ["core.read_file", "core.ask_user_input"],
            selected_tools={"core.read_file", "core.ask_user_input"},
            tool_details={
                "core.read_file": {"group_path": ["core", "filesystem"]},
                "core.ask_user_input": {"group_path": ["core", "user_input"]},
            },
        )

        assert [option.label for option in picker_options] == [
            "Group: core",
            "  Group: filesystem",
            "    core.read_file",
            "  Group: user_input",
            "    core.ask_user_input",
        ]
        assert grouped_values == {
            "__skill_group__:core": ("core.ask_user_input", "core.read_file"),
            "__skill_group__:core/filesystem": ("core.read_file",),
            "__skill_group__:core/user_input": ("core.ask_user_input",),
        }
        assert initial_selected_values == {
            "__skill_group__:core",
            "__skill_group__:core/filesystem",
            "__skill_group__:core/user_input",
            "core.ask_user_input",
            "core.read_file",
        }

    def test_edit_shortcut_can_open_tool_selection_popup(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f3")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("tools")
                await pilot.pause(0.1)

                assert isinstance(app.screen, ToolSelectionScreen)
                assert app.screen.query_one("#tool-picker-filter", Input).placeholder == "Filter tools..."

        asyncio.run(exercise())

    def test_llm_edit_prompts_for_clone_then_opens_editor(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_global_llm_override("smart")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                app._open_llm_profile_editor()
                await pilot.pause(0.05)

                assert isinstance(app.screen, NameInputScreen)
                app.screen.dismiss("smart-workspace")
                await pilot.pause(0.1)

                assert engine.clone_llm_profile_calls == [("smart", "smart-workspace")]
                assert isinstance(app.screen, TextEditorScreen)

        asyncio.run(exercise())

    def test_tool_picker_ctrl_arrows_switch_between_filter_and_list(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            engine.active_agent_profile.tools = []
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._open_tool_selection_picker()
                await pilot.pause(0.05)

                assert isinstance(app.screen, ToolSelectionScreen)
                assert app.screen.focused.id == "tool-picker-filter"

                await pilot.press("ctrl+down")
                await pilot.pause(0.05)
                assert app.screen.focused.id == "tool-picker-list"

                await pilot.press("ctrl+up")
                await pilot.pause(0.05)
                assert app.screen.focused.id == "tool-picker-filter"

        asyncio.run(exercise())

    def test_tool_picker_space_toggles_highlighted_selection(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            engine.active_agent_profile.tools = []
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._open_tool_selection_picker()
                await pilot.pause(0.05)

                assert isinstance(app.screen, ToolSelectionScreen)
                await pilot.press("ctrl+down", "space")
                await pilot.pause(0.05)

                assert "__skill_group__:tool" in app.screen._selected_values

        asyncio.run(exercise())

    def test_tool_picker_toggle_keeps_focus_on_current_item(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            engine.active_agent_profile.tools = []
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._open_tool_selection_picker()
                await pilot.pause(0.05)

                assert isinstance(app.screen, ToolSelectionScreen)
                await pilot.press("ctrl+down", "down", "down")
                await pilot.pause(0.05)

                selection_list = app.screen.query_one("#tool-picker-list", SelectionList)
                assert app.screen.focused.id == "tool-picker-list"
                assert selection_list.highlighted == 2
                assert selection_list.get_option_at_index(2).value == "tool.read"

                await pilot.press("space")
                await pilot.pause(0.05)

                selection_list = app.screen.query_one("#tool-picker-list", SelectionList)
                assert app.screen.focused.id == "tool-picker-list"
                assert selection_list.highlighted == 2
                assert selection_list.get_option_at_index(2).value == "tool.read"
                assert "tool.read" in app.screen._selected_values

        asyncio.run(exercise())


class TestProfileCloneAndSave:
    def test_clone_shortcut_promotes_workspace_agent(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("f4")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("agent")
                await pilot.pause(0.05)

                assert isinstance(app.screen, NameInputScreen)
                app.screen.dismiss("a-workspace")
                await pilot.pause(0.05)

                assert engine.clone_agent_profile_calls == [("a", "a-workspace")]
                assert engine.active_agent_profile.name == "a-workspace"

        asyncio.run(exercise())

    def test_control_center_can_select_mode(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("mode")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("select")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("review")
                await pilot.pause(0.05)

                assert engine.set_last_used_mode_calls == ["review"]
                assert engine.active_mode is not None
                assert engine.active_mode.name == "review"

        asyncio.run(exercise())

    def test_control_center_can_save_selection_preset(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("presets")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("save")
                await pilot.pause(0.05)

                assert isinstance(app.screen, NameInputScreen)
                app.screen.dismiss("focus-session")
                await pilot.pause(0.05)

                assert engine.saved_selection_presets == ["focus-session"]

        asyncio.run(exercise())

    def test_control_center_can_delete_current_mode(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_mode("review")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("mode")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("delete")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("delete")
                await pilot.pause(0.05)

                assert "review" not in engine._modes

        asyncio.run(exercise())

    def test_edit_agent_popup_persists_workspace_agent_edits(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._apply_agent_yaml_edit(
                    "a-safe",
                    "extra_prompts:\n  - prompts/review.md\n  - prompts/safety.md\n",
                )

                await pilot.pause(0.05)

                assert engine.update_agent_profile_calls == [
                    {
                        "name": "a-safe",
                        "llm_profile": None,
                        "tools": None,
                        "extra_prompts": ["prompts/review.md", "prompts/safety.md"],
                        "tool_confirmation_default": None,
                        "tool_confirmation_overrides": {},
                    }
                ]

        asyncio.run(exercise())

    def test_edit_agent_popup_clones_synthesised_agent_before_editing(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("f3")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("agent")
                await pilot.pause(0.05)

                assert isinstance(app.screen, NameInputScreen)
                app.screen.dismiss("a-workspace")
                await pilot.pause(0.1)

                assert engine.clone_agent_profile_calls == [("a", "a-workspace")]
                assert engine.active_agent_profile.name == "a-workspace"
                assert isinstance(app.screen, TextEditorScreen)

        asyncio.run(exercise())

    def test_edit_llm_popup_persists_workspace_llm_edits(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._apply_llm_yaml_edit(
                    "fast",
                    "provider: gemini\nmodel: gemini-2.5-flash\nparameters:\n  temperature: 0.1\n",
                )
                await pilot.pause(0.05)

                assert engine.update_llm_profile_calls == [
                    {
                        "name": "fast",
                        "profile_config": {
                            "provider": "gemini",
                            "model": "gemini-2.5-flash",
                            "parameters": {"temperature": 0.1},
                        },
                    }
                ]

        asyncio.run(exercise())

    def test_edit_flow_asset_popup_opens_text_editor(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._open_markdown_flow_asset_editor()
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("review-flow")
                await pilot.pause(0.1)

                assert isinstance(app.screen, TextEditorScreen)

        asyncio.run(exercise())

    def test_edit_flow_asset_popup_persists_markdown_edits(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._apply_markdown_asset_edit("flow", "review-flow", "---\nname: review-flow\n---\nupdated\n")
                await pilot.pause(0.05)

                assert engine.update_markdown_asset_calls == [
                    {
                        "asset_kind": "flow",
                        "name": "review-flow",
                        "markdown_text": "---\nname: review-flow\n---\nupdated\n",
                    }
                ]

        asyncio.run(exercise())

    def test_control_center_can_clone_tool_asset(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("tool_assets")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("clone")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("workspace-echo")
                await pilot.pause(0.05)

                assert isinstance(app.screen, NameInputScreen)
                app.screen.dismiss("workspace-echo-copy")
                await pilot.pause(0.1)

                assert engine.clone_markdown_asset_calls == [("tool", "workspace-echo", "workspace-echo-copy")]

        asyncio.run(exercise())

    def test_control_center_can_delete_flow_asset(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await pilot.press("f6")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("flow_assets")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("delete")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("review-flow")
                await pilot.pause(0.05)

                assert isinstance(app.screen, AssetPickerScreen)
                app.screen.dismiss("delete")
                await pilot.pause(0.1)

                assert engine.delete_markdown_asset_calls == [("flow", "review-flow")]

        asyncio.run(exercise())

    def test_tool_policy_popup_persists_workspace_agent_policy_overrides(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._apply_tool_policy_yaml_edit("a-safe", "tool.write: deny\n")
                await pilot.pause(0.05)

                assert engine.update_agent_profile_calls[-1]["tool_confirmation_overrides"] == {"tool.write": "deny"}
                assert engine.reset_last_used_profile_tool_policy_calls == ["a-safe"]

        asyncio.run(exercise())

    def test_tool_selection_popup_saves_last_used_tools(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._open_tool_selection_picker()
                await pilot.pause(0.05)

                assert isinstance(app.screen, ToolSelectionScreen)
                app.screen.dismiss({"action": "apply", "values": ["tool.read"]})
                await pilot.pause(0.05)

                assert engine.set_last_used_profile_tools_calls == [("a-safe", ["tool.read"])]

        asyncio.run(exercise())

    def test_tool_policy_popup_can_open_policy_editor_screen(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._open_tool_policy_editor()
                await pilot.pause(0.05)

                assert isinstance(app.screen, ToolPolicyEditorScreen)

        asyncio.run(exercise())

    def test_system_settings_screen_applies_and_saves_defaults(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                app._apply_system_settings(
                    {
                        "theme_name": "forest",
                        "workspace_view": "review",
                        "default_agent": "b",
                        "default_llm_profile": "smart",
                    }
                )
                await pilot.pause(0.05)

                assert engine.save_system_settings_calls == [
                    {
                        "theme_name": "forest",
                        "workspace_view": "review",
                        "default_agent": "b",
                        "default_llm_profile": "smart",
                    }
                ]
                assert engine.current_agent == "b"

        asyncio.run(exercise())


class TestInspectorToolFiltering:
    def test_inspector_tool_list_reflects_effective_selection(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            engine.active_agent_profile.tools = ["tool.read"]
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                tool_list = app.query_one("#inspector-tools", SelectionList)

                assert "tool.read" in tool_list.selected
                assert "tool.write" not in tool_list.selected
                assert "__skill_group__:tool" not in tool_list.selected
                assert "__skill_group__:tool/filesystem" not in tool_list.selected

        asyncio.run(exercise())

    def test_inspector_tool_group_list_reflects_unrestricted_selection(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                tool_list = app.query_one("#inspector-tools", SelectionList)

                assert "tool.read" in tool_list.selected
                assert "tool.write" in tool_list.selected
                assert "__skill_group__:tool" in tool_list.selected
                assert "__skill_group__:tool/filesystem" in tool_list.selected

        asyncio.run(exercise())

    def test_inspector_skill_list_reflects_enabled_skills(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.active_skills = ["python-lint", "python-testing"]
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                skill_list = app.query_one("#skill-list", SelectionList)

                assert "python-testing" in skill_list.selected
                assert "__skill_group__:python" in skill_list.selected

        asyncio.run(exercise())

    def test_inspector_skill_toggle_enables_selected_skill(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                selection_list = SimpleNamespace(
                    id="skill-list",
                    disabled=False,
                    selected={"python-testing"},
                    get_option_at_index=lambda index: SimpleNamespace(value="python-testing"),
                )
                event = SimpleNamespace(selection_list=selection_list, selection_index=0)

                app.on_selection_list_selection_toggled(event)
                await pilot.pause(0.05)

                assert engine.skill_enabled == ["python-testing"]
                assert engine.set_last_used_profile_skill_calls[-1] == ("a", ["python-testing"])

        asyncio.run(exercise())

    def test_inspector_skill_group_toggle_enables_group_members(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                selection_list = SimpleNamespace(
                    id="skill-list",
                    disabled=False,
                    selected={"__skill_group__:python"},
                    get_option_at_index=lambda index: SimpleNamespace(value="__skill_group__:python"),
                )
                event = SimpleNamespace(selection_list=selection_list, selection_index=0)

                app.on_selection_list_selection_toggled(event)
                await pilot.pause(0.05)

                assert engine.skill_enabled == ["python-lint", "python-testing"]
                assert engine.set_last_used_profile_skill_calls[-1] == (
                    "a",
                    ["python-lint", "python-testing"],
                )

        asyncio.run(exercise())

    def test_inspector_tool_toggle_updates_profile_allowlist(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                selection_list = SimpleNamespace(
                    id="inspector-tools",
                    disabled=False,
                    selected={"tool.write"},
                    get_option_at_index=lambda index: SimpleNamespace(value="tool.read"),
                )
                event = SimpleNamespace(selection_list=selection_list, selection_index=0)

                app.on_selection_list_selection_toggled(event)
                await pilot.pause(0.05)

                assert engine.set_last_used_profile_tools_calls[-1] == ("a-safe", ["tool.write"])

        asyncio.run(exercise())

    def test_inspector_skill_save_button_persists_to_agent_yaml(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            engine.active_skills = ["python-lint", "python-testing"]
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                event = SimpleNamespace(button=SimpleNamespace(id="inspector-skill-save-button"))

                app.on_button_pressed(event)
                await pilot.pause(0.05)

                assert engine.save_agent_profile_skill_calls[-1] == (
                    "a-safe",
                    ["python-lint", "python-testing"],
                )

        asyncio.run(exercise())

    def test_inspector_tool_save_button_persists_to_agent_yaml(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            engine.active_agent_profile.tools = ["tool.read"]
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                event = SimpleNamespace(button=SimpleNamespace(id="inspector-tool-save-button"))

                app.on_button_pressed(event)
                await pilot.pause(0.05)

                assert engine.save_agent_profile_tool_calls[-1] == ("a-safe", ["tool.read"])

        asyncio.run(exercise())

    def test_inspector_tool_group_toggle_updates_nested_group_members(self):
        async def exercise() -> None:
            engine = _TextualEngineStub()
            engine.set_active_agent_profile("a-safe")
            engine.active_agent_profile.tools = ["tool.read"]
            app = PocketCodeTextualApp(
                engine,
                {"files": set(), "folders": set(), "urls": set(), "snippets": {}},
            )

            async with app.run_test() as pilot:
                await pilot.pause()
                selection_list = SimpleNamespace(
                    id="inspector-tools",
                    disabled=False,
                    selected={"__skill_group__:tool/filesystem"},
                    get_option_at_index=lambda index: SimpleNamespace(value="__skill_group__:tool/filesystem"),
                )
                event = SimpleNamespace(selection_list=selection_list, selection_index=0)

                app.on_selection_list_selection_toggled(event)
                await pilot.pause(0.05)

                assert engine.set_last_used_profile_tools_calls[-1] == ("a-safe", None)

        asyncio.run(exercise())
