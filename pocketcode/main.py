from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Dict

from dotenv import load_dotenv

from pocketcode.cli.command_handler import handle_command
from pocketcode.config.loader import load_settings, resolve_settings_path
from pocketcode.core.engine import PocketCodeEngine

logger = logging.getLogger(__name__)


def _configure_logging(log_level: str) -> None:
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(numeric_level)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(numeric_level)
    stream_handler.setFormatter(formatter)

    file_handler = logging.FileHandler("pocketcode.log")
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)


def _print_startup(engine: PocketCodeEngine) -> None:
    status = engine.status()
    print("Pocketcode plugin runtime ready.")
    print(f"Runtime flow (internal): {status.get('runtime_workflow')}")
    print(f"Agent: {status['agent'] or 'auto'}")
    print(f"Global LLM override: {status['global_llm_override'] or 'none'}")


def _run_basic_interactive_cli(engine: PocketCodeEngine, cli_context: Dict[str, Any]) -> None:
    print("Textual UI unavailable. Using basic interactive CLI.")
    print("Type /help for commands. Ctrl+C or /exit to quit.")

    while True:
        agent = engine.get_current_agent() or "auto"
        try:
            user_input = input(f"({agent}) > ")
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
            response = engine.process_request(user_input=user_input, cli_context=cli_context)
            print(response)
        except Exception as exc:
            logger.error("Request processing failed: %s", exc, exc_info=True)
            print(f"Error processing request: {exc}")


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
    parser.add_argument(
        "--workflow",
        help="Deprecated. Workflow selection is internal; use --agent for interactive selection.",
    )
    parser.add_argument("--agent", help="Initial agent name override.")
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
    _configure_logging(log_level)

    try:
        engine = PocketCodeEngine(config=config, workspace_root=os.getcwd())
    except Exception as exc:
        logger.error("Failed to initialize PocketCodeEngine: %s", exc, exc_info=True)
        print(f"Engine initialization failed: {exc}")
        sys.exit(1)

    try:
        if args.workflow:
            print(
                "Ignoring --workflow. Workflow selection is internal; use --agent for runtime control."
            )
        if args.agent:
            engine.set_agent(None if args.agent.lower() == "auto" else args.agent)
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
    }

    if args.prompt is not None:
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
                )
                if command_result not in (None, "__exit__"):
                    print(command_result)
            else:
                response = engine.process_request(user_input=request, cli_context=cli_context)
                print(response)
        except Exception as exc:
            logger.error("Request processing failed: %s", exc, exc_info=True)
            print(f"Error processing request: {exc}")
            sys.exit(1)
        return

    _print_startup(engine)
    if force_basic_cli:
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
        run_textual_cli(engine=engine, cli_context=cli_context)
    except Exception as exc:
        logger.error("Textual UI failed to start: %s", exc, exc_info=True)
        _run_basic_interactive_cli(engine=engine, cli_context=cli_context)


if __name__ == "__main__":
    run()
