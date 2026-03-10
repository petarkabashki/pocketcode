from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import Any, Dict

from dotenv import load_dotenv

from pocketcode.cli.debugger_commands import (
    build_debugger_until_predicate as _build_debugger_until_predicate,
    lookup_path as _lookup_path,
    parse_debug_step_count as _parse_debug_step_count,
    parse_debugger_condition as _parse_debugger_condition,
    resolve_debugger_value as _resolve_debugger_value,
    split_debugger_command as _split_debugger_command,
)
from pocketcode.cli.runtime_events import format_runtime_event
from pocketcode.cli.user_interaction import request_interaction_from_console
from pocketcode.cli.command_handler import handle_command
from pocketcode.config.loader import load_settings, resolve_settings_path
from pocketcode.core.engine import PocketCodeEngine

logger = logging.getLogger(__name__)


def _configure_logging(log_level: str, *, stream: bool = True) -> None:
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(numeric_level)

    file_handler = logging.FileHandler("pocketcode.log")
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)

    if stream:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(numeric_level)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)


def _print_startup(engine: PocketCodeEngine) -> None:
    status = engine.status()
    print("Pocketcode runtime ready.")
    print(f"Internal flow: {status.get('runtime_flow') or 'internal-flow'}")
    print(f"Selected flow: {status.get('flow') or 'auto'}")
    print(f"Agent: {status.get('agent') or 'none'}")
    print(f"Global LLM override: {status['global_llm_override'] or 'none'}")


def _run_basic_interactive_cli(engine: PocketCodeEngine, cli_context: Dict[str, Any]) -> None:
    cli_context["interface"] = "basic"
    cli_context["debug_request_runner"] = lambda request: _run_request_with_debugger(
        engine=engine,
        user_input=request,
        cli_context=cli_context,
        bridge_user_input=True,
    )
    print("Textual UI unavailable. Using basic interactive CLI.")
    print("Type /help for commands. Ctrl+C or /exit to quit.")

    while True:
        flow = engine.get_current_flow() if hasattr(engine, "get_current_flow") else engine.get_current_agent()
        flow = flow or "auto"
        try:
            user_input = input(f"({flow}) > ")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting Pocketcode.")
            return

        if not user_input.strip():
            continue

        if user_input.startswith("/"):
            command_result = handle_command(
                command_input=user_input,
                engine=engine,
                cli_context=cli_context,
            )
            if command_result == "__exit__":
                return
            continue

        try:
            response = _run_request_with_live_events(
                engine=engine,
                user_input=user_input,
                cli_context=cli_context,
                bridge_user_input=True,
            )
            print(response)
        except Exception as exc:
            logger.error("Request processing failed: %s", exc, exc_info=True)
            print(f"Error processing request: {exc}")


def _run_request_with_live_events(
    *,
    engine: PocketCodeEngine,
    user_input: str,
    cli_context: Dict[str, Any],
    bridge_user_input: bool,
) -> str:
    handle = engine.start_request(
        user_input=user_input,
        cli_context=cli_context,
        bridge_user_input=bridge_user_input,
    )
    resolved_prompts: set[str] = set()

    try:
        while not handle.is_done:
            _drain_live_events(handle=handle, resolved_prompts=resolved_prompts, bridge_user_input=bridge_user_input)
            if not handle.is_done:
                time.sleep(0.05)
    except KeyboardInterrupt:
        if handle.cancel("Run cancelled from CLI interrupt."):
            print("\nStop requested. Waiting for the active step to yield...")
        while not handle.is_done:
            _drain_live_events(handle=handle, resolved_prompts=resolved_prompts, bridge_user_input=bridge_user_input)
            if not handle.is_done:
                time.sleep(0.05)

    _drain_live_events(handle=handle, resolved_prompts=resolved_prompts, bridge_user_input=bridge_user_input)
    return handle.wait(timeout=1.0)


def _run_request_with_debugger(
    *,
    engine: PocketCodeEngine,
    user_input: str,
    cli_context: Dict[str, Any],
    bridge_user_input: bool,
) -> str:
    handle = engine.start_request(
        user_input=user_input,
        cli_context=cli_context,
        bridge_user_input=bridge_user_input,
        debug=True,
    )
    resolved_prompts: set[str] = set()
    pause_banner_shown = False

    try:
        while not handle.is_done:
            _drain_live_events(handle=handle, resolved_prompts=resolved_prompts, bridge_user_input=bridge_user_input)
            if handle.is_debug_paused:
                if not pause_banner_shown:
                    print("[debug] Interactive debugger attached. Type 'help' for commands.")
                    pause_banner_shown = True
                _run_debugger_prompt(handle=handle)
                continue
            time.sleep(0.05)
    except KeyboardInterrupt:
        if handle.cancel("Run cancelled from debugger interrupt."):
            print("\nStop requested. Waiting for the active step to yield...")
        handle.continue_debugger()
        while not handle.is_done:
            _drain_live_events(handle=handle, resolved_prompts=resolved_prompts, bridge_user_input=bridge_user_input)
            if handle.is_debug_paused:
                handle.continue_debugger()
            if not handle.is_done:
                time.sleep(0.05)

    _drain_live_events(handle=handle, resolved_prompts=resolved_prompts, bridge_user_input=bridge_user_input)
    return handle.wait(timeout=1.0)


def _run_debugger_prompt(*, handle: Any) -> None:
    paused_event = handle.debug_pause_event or {}
    _print_debug_pause(paused_event, handle.get_debug_snapshot(), until_label=handle.debug_until_label)

    while handle.is_debug_paused and not handle.is_done:
        try:
            command = input("(debug) > ").strip()
        except (KeyboardInterrupt, EOFError):
            command = "quit"

        parts = _split_debugger_command(command)
        if not parts:
            handle.step_debugger()
            return
        normalized = parts[0].lower()
        if normalized in {"n", "next", "s", "step"}:
            count = _parse_debug_step_count(parts[1:] if len(parts) > 1 else [])
            if count is None:
                print("[debug] Usage: next [count]")
                continue
            handle.step_debugger(count=count)
            return
        if normalized in {"c", "cont", "continue"}:
            handle.continue_debugger()
            return
        if normalized in {"p", "pause", "status", "where"}:
            _print_debug_pause(paused_event, handle.get_debug_snapshot(), until_label=handle.debug_until_label)
            continue
        if normalized in {"steps", "timeline"}:
            _print_debug_steps(handle.get_debug_snapshot())
            continue
        if normalized in {"break", "b"}:
            breakpoint_command = parts[1:]
            breakpoint_config = _build_debugger_until_predicate(breakpoint_command)
            if breakpoint_config is None:
                print("[debug] Usage: break <node|agent|tool|event|when> ...")
                continue
            predicate, label = breakpoint_config
            breakpoint_id = handle.add_debug_breakpoint(predicate, label=label)
            print(f"[debug] Breakpoint {breakpoint_id} added: {label}")
            continue
        if normalized in {"breaks", "bp"}:
            _print_debug_breakpoints(handle)
            continue
        if normalized == "clear":
            if len(parts) == 1 or parts[1].lower() == "all":
                cleared = handle.clear_all_debug_breakpoints()
                print(f"[debug] Cleared {cleared} breakpoint(s).")
                continue
            try:
                breakpoint_id = int(parts[1])
            except (TypeError, ValueError):
                print("[debug] Usage: clear <breakpoint_id|all>")
                continue
            if handle.clear_debug_breakpoint(breakpoint_id):
                print(f"[debug] Cleared breakpoint {breakpoint_id}.")
            else:
                print(f"[debug] Breakpoint {breakpoint_id} not found.")
            continue
        if normalized == "until":
            until_command = parts[1:]
            predicate_config = _build_debugger_until_predicate(until_command)
            if predicate_config is None:
                print("[debug] Usage: until <node|agent|tool|event|when> ...")
                continue
            predicate, label = predicate_config
            handle.continue_until_debugger(predicate, label=label)
            return
        if normalized in {"q", "quit", "cancel"}:
            if handle.cancel("Run cancelled from debugger."):
                print("[debug] Cancellation requested.")
            handle.continue_debugger()
            return
        if normalized in {"h", "help", "?"}:
            print(
                "Debugger commands: next [count], continue, until node <id>, until agent <name>, "
                "until tool <name>, until event <type>, until when <path> == <value>, "
                "break <...>, breaks, clear <id|all>, status, steps, quit, help"
            )
            continue
        print(
            "Unknown debugger command. Use: next [count], continue, until ..., break <...>, "
            "breaks, clear <id|all>, status, steps, quit, help"
        )


def _print_debug_pause(paused_event: Dict[str, Any], snapshot: Dict[str, Any], *, until_label: str | None = None) -> None:
    event_type = paused_event.get("type") or "event"
    message = format_runtime_event(paused_event) or f"Paused at {event_type}."
    print(f"[debug] Paused: {message}")
    if paused_event.get("debug_breakpoint_id"):
        print(
            f"[debug] Breakpoint hit: #{paused_event.get('debug_breakpoint_id')} "
            f"{paused_event.get('debug_breakpoint_label') or ''}".rstrip()
        )
    if until_label:
        print(f"[debug] Stop condition: {until_label}")
    print(f"[debug] Active agent: {snapshot.get('active_agent') or 'unknown'}")
    if snapshot.get("active_node_id"):
        print(
            f"[debug] Active node: {snapshot.get('active_node_id')} "
            f"({snapshot.get('active_node_kind') or 'node'})"
        )
    if snapshot.get("current_llm_profile") or snapshot.get("current_llm_model"):
        print(
            "[debug] LLM: "
            f"{snapshot.get('current_llm_profile') or 'none'} "
            f"({snapshot.get('current_llm_model') or '-'})"
        )
    if snapshot.get("pending_tool"):
        print(f"[debug] Pending tool: {snapshot.get('pending_tool')}")
    if snapshot.get("pending_handoff_agent"):
        print(f"[debug] Pending handoff: {snapshot.get('pending_handoff_agent')}")
    if snapshot.get("last_agent_decision"):
        print(f"[debug] Last agent decision: {snapshot.get('last_agent_decision')}")
    if snapshot.get("last_tool_route"):
        print(f"[debug] Last tool route: {snapshot.get('last_tool_route')}")
    if snapshot.get("error_message"):
        print(f"[debug] Error: {snapshot.get('error_message')}")
    print(
        f"[debug] Steps so far: {snapshot.get('step_count', 0)} | "
        f"Events: {snapshot.get('runtime_event_count', 0)}"
    )


def _print_debug_breakpoints(handle: Any) -> None:
    breakpoints = handle.list_debug_breakpoints()
    if not breakpoints:
        print("[debug] No breakpoints set.")
        return
    print("[debug] Breakpoints:")
    for item in breakpoints:
        print(f"  {item.get('id')}. {item.get('label')}")


def _print_debug_steps(snapshot: Dict[str, Any]) -> None:
    steps = snapshot.get("steps", [])
    if not isinstance(steps, list) or not steps:
        print("[debug] No recorded steps yet.")
        return
    print("[debug] Step timeline:")
    for step in steps:
        if not isinstance(step, dict):
            continue
        duration = step.get("duration_ms")
        duration_suffix = f" [{float(duration):.1f}ms]" if isinstance(duration, (int, float)) else ""
        print(
            f"  {step.get('index')}. {step.get('kind')} "
            f"({step.get('status')}){duration_suffix} {step.get('summary')}"
        )


def _drain_live_events(
    *,
    handle: Any,
    resolved_prompts: set[str],
    bridge_user_input: bool,
) -> None:
    for event in handle.drain_events():
        message = format_runtime_event(event)
        if message:
            print(f"[runtime] {message}")

        if not bridge_user_input:
            continue

        if event.get("type") == "interaction_requested":
            request_id = str(event.get("request_id") or "")
            if not request_id or request_id in resolved_prompts:
                continue

            response = request_interaction_from_console(event)
            if handle.resolve_interaction(request_id, response):
                resolved_prompts.add(request_id)
            continue

        if event.get("type") != "user_input_requested":
            continue

        prompt_id = str(event.get("prompt_id") or "")
        if not prompt_id or prompt_id in resolved_prompts:
            continue

        response = input(str(event.get("prompt") or "Provide input"))
        if handle.resolve_user_input(prompt_id, response):
            resolved_prompts.add(prompt_id)


def run() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Pocketcode AI Assistant CLI")
    parser.add_argument(
        "--config",
        default=None,
        help=(
            "Deprecated. Pocketcode always loads config from ./pocketcode.yml in the workspace root."
        ),
    )
    parser.add_argument("--flow", help="Initial flow name override.")
    parser.add_argument("--llm", help="Global LLM profile override.")
    parser.add_argument(
        "--prompt",
        help="Run one request non-interactively and exit.",
    )
    parser.add_argument(
        "--auto-confirm-tools",
        action="store_true",
        help="Automatically approve tool execution regardless of runtime defaults.",
    )
    args = parser.parse_args()

    force_basic_cli = False
    if args.prompt is None:
        stdin_is_tty = sys.stdin.isatty()
        stdout_is_tty = sys.stdout.isatty()

        if not stdin_is_tty:
            piped_prompt = sys.stdin.read().strip()
            if not piped_prompt:
                print("Pocketcode requires interactive stdin for chat mode.")
                print(
                    "Use a terminal session, pipe input, or run one-shot mode with: "
                    "pocketcode --prompt \"your request\""
                )
                sys.exit(1)
            args.prompt = piped_prompt

        if args.prompt is None and not stdout_is_tty:
            print("Detected non-interactive stdout. Falling back to basic interactive CLI.")
            force_basic_cli = True

    try:
        if args.config:
            print("Ignoring --config. Pocketcode always loads configuration from ./pocketcode.yml.")
        resolved_config_path = resolve_settings_path(args.config, os.getcwd())
        config = load_settings(settings_path=resolved_config_path, workspace_root=os.getcwd())
    except Exception as exc:
        failed_path = os.path.join(os.getcwd(), "pocketcode.yml")
        print(f"Failed to load configuration from '{failed_path}': {exc}")
        sys.exit(1)

    log_level = str(config.get("runtime", {}).get("log_level", os.environ.get("LOG_LEVEL", "INFO")))
    _configure_logging(log_level, stream=force_basic_cli or args.prompt is not None)

    try:
        engine = PocketCodeEngine(config=config, workspace_root=os.getcwd())
    except Exception as exc:
        logger.error("Failed to initialize PocketCodeEngine: %s", exc, exc_info=True)
        print(f"Engine initialization failed: {exc}")
        sys.exit(1)

    try:
        selected_flow = args.flow
        if selected_flow:
            engine.set_flow(None if selected_flow.lower() == "auto" else selected_flow)
        if args.llm:
            engine.set_global_llm_override(args.llm)
        if args.auto_confirm_tools:
            engine.auto_confirm_tools = True
    except Exception as exc:
        print(f"Invalid startup override: {exc}")
        sys.exit(1)

    cli_context: Dict[str, Any] = {
        "files": set(),
        "folders": set(),
        "urls": set(),
        "snippets": {},
        "interface": None,
    }

    if args.prompt is not None:
        cli_context["interface"] = "one-shot"
        request = args.prompt.strip()
        if not request:
            print("No prompt provided. Pass text with --prompt.")
            sys.exit(1)
        try:
            if request.startswith("/"):
                command_result = handle_command(
                    command_input=request,
                    engine=engine,
                    cli_context=cli_context,
                    active_run=None,
                )
                if command_result not in (None, "__exit__"):
                    print(command_result)
            else:
                response = _run_request_with_live_events(
                    engine=engine,
                    user_input=request,
                    cli_context=cli_context,
                    bridge_user_input=False,
                )
                print(response)
        except Exception as exc:
            logger.error("Request processing failed: %s", exc, exc_info=True)
            print(f"Error processing request: {exc}")
            sys.exit(1)
        return

    if force_basic_cli:
        cli_context["interface"] = "basic"
        _print_startup(engine)
        _run_basic_interactive_cli(engine=engine, cli_context=cli_context)
        return

    try:
        from pocketcode.cli.textual_app import run_textual_cli
    except ModuleNotFoundError as exc:
        if getattr(exc, "name", "") == "textual":
            print("Interactive mode requires the 'textual' package.")
            print("Install dependencies with: pip install -e .")
            sys.exit(1)
        raise

    try:
        cli_context["interface"] = "textual"
        run_textual_cli(engine=engine, cli_context=cli_context)
    except Exception as exc:
        logger.error("Textual UI failed to start: %s", exc, exc_info=True)
        cli_context["interface"] = "basic"
        _run_basic_interactive_cli(engine=engine, cli_context=cli_context)


if __name__ == "__main__":
    run()
