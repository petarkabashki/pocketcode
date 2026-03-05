from __future__ import annotations

import asyncio
import io
import logging
from contextlib import redirect_stdout
from typing import Any, Dict

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.suggester import SuggestFromList
from textual.widgets import Footer, Header, Input, Static, TextArea

from pocketcode.cli.command_handler import handle_command
from pocketcode.core.engine import PocketCodeEngine

logger = logging.getLogger(__name__)


class PocketCodeTextualApp(App[None]):
    BINDINGS = [
        Binding("tab", "complete_input", "Complete Input", priority=True),
        Binding("ctrl+]", "next_agent", "Next Agent", priority=True),
        Binding("ctrl+[", "next_llm", "Next LLM", priority=True),
        Binding("ctrl+t", "toggle_stats", "Toggle Stats"),
        Binding("ctrl+space", "complete_input", "Complete Input"),
        Binding("ctrl+shift+a", "copy_output", "Copy Output"),
        Binding("ctrl+y", "copy_last_response", "Copy Last"),
        Binding("ctrl+r", "reload_runtime", "Reload"),
        Binding("ctrl+l", "clear_output", "Clear Output"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    CSS = """
    Screen {
        layout: vertical;
    }

    #status {
        height: 2;
        padding: 0 1;
        background: $boost;
        content-align: left middle;
    }

    #stats {
        height: 2;
        padding: 0 1;
        background: $surface;
        content-align: left middle;
    }

    #root {
        height: 1fr;
    }

    #output {
        height: 1fr;
        margin: 0 1;
        border: round $primary;
    }

    #input {
        margin: 0 1 1 1;
    }
    """

    def __init__(self, engine: PocketCodeEngine, cli_context: Dict[str, Any]) -> None:
        super().__init__()
        self._engine = engine
        self._cli_context = cli_context
        self._busy = False
        self._show_stats = True
        self._output_lines: list[str] = []
        self._last_assistant_response: str = ""
        self._suggestions: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(id="status")
        yield Static(id="stats")
        with Vertical(id="root"):
            yield TextArea(
                "",
                id="output",
                read_only=True,
            )
            yield Input(
                id="input",
                placeholder=(
                    "Type a request or /command. Tab=complete Ctrl+]=agent Ctrl+[=LLM "
                    "Ctrl+T=stats Ctrl+Shift+A=copy output"
                ),
            )
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_suggestions()
        self._update_status()
        self._update_stats()
        self._write_info("Pocketcode Textual UI ready. Use /help for commands.")
        self.query_one("#input", Input).focus()

    def _refresh_suggestions(self) -> None:
        commands = [
            "/help",
            "/list",
            "/set",
            "/agents",
            "/agent",
            "/components",
            "/llms",
            "/llm",
            "/llm-agent",
            "/llm-node",
            "/llm-handoff",
            "/tools",
            "/reload",
            "/status",
            "/context",
            "/confirm",
            "/copy",
            "/copy-all",
            "/exit",
            "/quit",
            "/ls",
            "/wf",
            "/ag",
            "/lm",
            "/la",
            "/ln",
            "/lh",
            "/st",
            "/r",
            "/q",
        ]
        words = sorted(
            set(
                commands
                + self._engine.list_agents()
                + self._engine.list_llm_profiles()
            )
        )
        self._suggestions = words
        self.query_one("#input", Input).suggester = SuggestFromList(words, case_sensitive=False)

    def _update_status(self) -> None:
        status = self._engine.status()
        runtime_flow = status.get("runtime_workflow") or "internal-flow"
        run_summary = status.get("last_run_summary", {}) if isinstance(status, dict) else {}
        current_agent = run_summary.get("current_agent") or status.get("agent") or "auto"

        agent_path = run_summary.get("agent_path", [])
        if isinstance(agent_path, list) and len(agent_path) > 1:
            agent_display = " -> ".join(str(name) for name in agent_path if isinstance(name, str))
        else:
            agent_display = str(current_agent)

        current_llm_profile = run_summary.get("current_llm_profile") or status.get("global_llm_override") or "none"
        current_llm_model = run_summary.get("current_llm_model") or "-"
        text = (
            f"Runtime flow: {runtime_flow} | Agent: {agent_display} | "
            f"LLM: {current_llm_profile} ({current_llm_model})"
        )
        self.query_one("#status", Static).update(text)

    def _write_info(self, text: str) -> None:
        self._append_output_line(f"info> {text}")

    def _write_error(self, text: str) -> None:
        self._append_output_line(f"error> {text}")

    def _write_user(self, text: str) -> None:
        self._append_output_line(f"you> {text}")

    def _write_assistant(self, text: str) -> None:
        self._append_output_line(f"assistant> {text}")
        self._last_assistant_response = text

    def _append_output_line(self, line: str) -> None:
        self._output_lines.append(line)
        output_widget = self.query_one("#output", TextArea)
        output_widget.text = "\n".join(self._output_lines)
        output_widget.scroll_end(animate=False)

    def _update_stats(self) -> None:
        stats_widget = self.query_one("#stats", Static)
        if not self._show_stats:
            stats_widget.display = False
            return

        stats_widget.display = True
        status = self._engine.status()
        run_summary = status.get("last_run_summary", {}) if isinstance(status, dict) else {}
        context_stats = run_summary.get("context_stats", {}) if isinstance(run_summary, dict) else {}
        if not isinstance(context_stats, dict) or not context_stats:
            snippets = self._cli_context.get("snippets", {})
            snippet_chars = 0
            if isinstance(snippets, dict):
                for value in snippets.values():
                    if isinstance(value, str):
                        snippet_chars += len(value)
            context_stats = {
                "files": len(self._cli_context.get("files", set()) or set()),
                "folders": len(self._cli_context.get("folders", set()) or set()),
                "urls": len(self._cli_context.get("urls", set()) or set()),
                "snippets": len(snippets) if isinstance(snippets, dict) else 0,
                "snippet_chars": snippet_chars,
            }
        llm_usage = run_summary.get("llm_usage", {}) if isinstance(run_summary, dict) else {}
        cost = run_summary.get("llm_cost_usd", 0.0) if isinstance(run_summary, dict) else 0.0

        files = context_stats.get("files", 0) if isinstance(context_stats, dict) else 0
        folders = context_stats.get("folders", 0) if isinstance(context_stats, dict) else 0
        urls = context_stats.get("urls", 0) if isinstance(context_stats, dict) else 0
        snippets = context_stats.get("snippets", 0) if isinstance(context_stats, dict) else 0
        snippet_chars = context_stats.get("snippet_chars", 0) if isinstance(context_stats, dict) else 0

        prompt_tokens = llm_usage.get("prompt_tokens", 0) if isinstance(llm_usage, dict) else 0
        completion_tokens = llm_usage.get("completion_tokens", 0) if isinstance(llm_usage, dict) else 0
        total_tokens = llm_usage.get("total_tokens", 0) if isinstance(llm_usage, dict) else 0

        text = (
            f"Context files={files} folders={folders} urls={urls} snippets={snippets} "
            f"snippet_chars={snippet_chars} | Tokens in={prompt_tokens} out={completion_tokens} "
            f"total={total_tokens} | Cost=${float(cost):.6f}"
        )
        stats_widget.update(text)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text or self._busy:
            return

        input_widget = self.query_one("#input", Input)
        input_widget.value = ""
        input_widget.disabled = True
        self._busy = True

        self._write_user(text)

        try:
            if text.startswith("/"):
                if text.lower() == "/copy":
                    self.action_copy_last_response()
                    return
                if text.lower() == "/copy-all":
                    self.action_copy_output()
                    return
                command_output, should_exit = await asyncio.to_thread(self._run_command_capture, text)
                if command_output:
                    self._write_info(command_output)
                if should_exit:
                    self.exit()
                    return
            else:
                response = await asyncio.to_thread(
                    self._engine.process_request,
                    text,
                    self._cli_context,
                )
                self._write_assistant(str(response))
        except Exception as exc:
            logger.error("Failed to process Textual input: %s", exc, exc_info=True)
            self._write_error(str(exc))
        finally:
            self._busy = False
            input_widget.disabled = False
            input_widget.focus()
            self._update_status()
            self._update_stats()

    def _run_command_capture(self, command_input: str) -> tuple[str, bool]:
        output = io.StringIO()
        with redirect_stdout(output):
            result = handle_command(
                command_input=command_input,
                engine=self._engine,
                cli_context=self._cli_context,
            )

        text = output.getvalue().strip()
        should_exit = result == "__exit__"
        return text, should_exit

    def action_next_agent(self) -> None:
        try:
            agents = self._engine.list_agents()
            if not agents:
                self._write_error("No agents are available.")
                return

            current = self._engine.get_current_agent()
            if current in agents:
                idx = agents.index(current)
                next_agent = agents[(idx + 1) % len(agents)]
            else:
                next_agent = agents[0]

            self._engine.set_agent(next_agent)
            self._write_info(f"Selected agent: {next_agent}")
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._update_status()

    def action_next_llm(self) -> None:
        try:
            profiles = self._engine.list_llm_profiles()
            if not profiles:
                self._write_error("No LLM profiles are available.")
                return

            current = self._engine.global_llm_override
            cycle = [None] + profiles
            try:
                idx = cycle.index(current)
            except ValueError:
                idx = 0
            next_value = cycle[(idx + 1) % len(cycle)]

            self._engine.set_global_llm_override(next_value)
            self._write_info(
                f"Global LLM override: {next_value if next_value is not None else 'none'}"
            )
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._update_status()

    def action_reload_runtime(self) -> None:
        try:
            self._engine.reload()
            self._refresh_suggestions()
            self._write_info("Reloaded plugins, agents, internal flows, tools, and LLM profile mappings.")
        except Exception as exc:
            self._write_error(str(exc))
        finally:
            self._update_status()
            self._update_stats()

    def action_clear_output(self) -> None:
        self.query_one("#output", TextArea).text = ""
        self._output_lines = []
        self._write_info("Cleared output.")

    def action_toggle_stats(self) -> None:
        self._show_stats = not self._show_stats
        self._update_stats()
        state = "shown" if self._show_stats else "hidden"
        self._write_info(f"Top stats {state}.")

    def action_copy_output(self) -> None:
        if not self._output_lines:
            self._write_error("No output to copy.")
            return
        text = "\n".join(self._output_lines)
        try:
            self.copy_to_clipboard(text)
            self._write_info("Copied full console output to clipboard.")
        except Exception as exc:
            self._write_error(f"Clipboard copy failed: {exc}")

    def action_copy_last_response(self) -> None:
        if not self._last_assistant_response:
            self._write_error("No assistant response available to copy.")
            return
        try:
            self.copy_to_clipboard(self._last_assistant_response)
            self._write_info("Copied last assistant response to clipboard.")
        except Exception as exc:
            self._write_error(f"Clipboard copy failed: {exc}")

    def action_complete_input(self) -> None:
        input_widget = self.query_one("#input", Input)
        prefix = input_widget.value
        if not prefix:
            return

        lowered_prefix = prefix.lower()
        for suggestion in self._suggestions:
            if suggestion.lower().startswith(lowered_prefix):
                input_widget.value = suggestion
                input_widget.cursor_position = len(suggestion)
                return


def run_textual_cli(engine: PocketCodeEngine, cli_context: Dict[str, Any]) -> None:
    app = PocketCodeTextualApp(engine=engine, cli_context=cli_context)
    app.run()
