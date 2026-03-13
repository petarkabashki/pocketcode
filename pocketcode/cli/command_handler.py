from __future__ import annotations

import logging
import shlex
from typing import Any, Dict, Optional

from pocketcode.core.engine import PocketCodeEngine
from pocketcode.cli.stackvm_commands import handle_stackvm_command, print_stackvm_help
from pocketcode.core.command_runtime import CommandResult

logger = logging.getLogger(__name__)

TEXTUAL_ONLY_COMMANDS = {"/copy", "/copy-all", "/view"}
TEXTUAL_VIEWS = ("chat", "control", "run")
TEXTUAL_COMMAND_SUGGESTIONS = [
    "/view",
    "/view list",
    "/view show",
    "/view switch chat",
    "/view switch control",
    "/view switch run",
]

BASE_COMMAND_SUGGESTIONS = [
    "/help",
    "/list",
    "/set",
    "/flows",
    "/flow",
    "/prompts",
    "/skills",
    "/skill",
    "/agents",
    "/agent",
    "/llms",
    "/llm",
    "/llm-flow",
    "/llm-agent",
    "/llm-handoff",
    "/tools",
    "/reload",
    "/debug",
    "/stop",
    "/cancel",
    "/status",
    "/context",
    "/confirm",
    "/session",
    "/session show",
    "/session list",
    "/session new",
    "/session resume",
    "/stackvm",
    "/stackvm list",
    "/stackvm create",
    "/stackvm inspect",
    "/stackvm run",
    "/stackvm debug",
    "/stackvm alter",
    "/agent list",
    "/agent show",
    "/agent switch",
    "/skill list",
    "/skill show",
    "/exit",
    "/quit",
    "/ls",
    "/ag",
    "/ap",
    "/lm",
    "/lf",
    "/la",
    "/lh",
    "/st",
    "/c",
    "/r",
    "/q",
]


def _list_flow_names(engine: PocketCodeEngine) -> list[str]:
    names = engine.list_flows() if hasattr(engine, "list_flows") else engine.list_agents()
    return sorted({str(name) for name in names})


def _list_agent_names(engine: PocketCodeEngine) -> list[str]:
    names = (
        engine.list_available_agents()
        if hasattr(engine, "list_available_agents")
        else engine.list_agent_profiles()
    )
    return sorted({str(name) for name in names})


def _get_current_flow_name(engine: PocketCodeEngine) -> str | None:
    getter = None
    if hasattr(engine, "get_current_flow"):
        getter = engine.get_current_flow
    elif hasattr(engine, "get_current_agent"):
        getter = engine.get_current_agent
    if getter is None:
        return None
    current = getter()
    return str(current) if current else None


def _get_active_agent_profile(engine: PocketCodeEngine) -> Any:
    if hasattr(engine, "get_agent"):
        return engine.get_agent()
    if hasattr(engine, "get_agent_profile"):
        return engine.get_agent_profile()
    return None


def _get_named_agent_profile(engine: PocketCodeEngine, name: str) -> Any:
    if hasattr(engine, "get_agent"):
        return engine.get_agent(name)
    if hasattr(engine, "get_agent_profile"):
        return engine.get_agent_profile(name)
    return None


def _list_user_agent_names(engine: PocketCodeEngine) -> list[str]:
    names = _list_agent_names(engine)
    visible: list[str] = []
    for name in names:
        profile = _get_named_agent_profile(engine, name)
        if profile is not None and getattr(profile, "source", None) == "synthesised":
            continue
        visible.append(name)
    return visible


def _skill_group_name(skill_name: str) -> str:
    cleaned = str(skill_name).strip()
    if not cleaned:
        return "other"
    if "-" in cleaned:
        return cleaned.split("-", 1)[0]
    if "." in cleaned:
        return cleaned.split(".", 1)[0]
    return "other"


def _print_grouped_skills(engine: PocketCodeEngine) -> None:
    skills = engine.list_skills() if hasattr(engine, "list_skills") else []
    active_skills = {
        skill.name if hasattr(skill, "name") else str(skill)
        for skill in (engine.get_active_skills() if hasattr(engine, "get_active_skills") else [])
    }
    print("Available skills:")
    if not skills:
        print("  (none)")
        return

    grouped: dict[str, list[str]] = {}
    for name in sorted({str(skill_name) for skill_name in skills}):
        grouped.setdefault(_skill_group_name(name), []).append(name)

    for group_name in sorted(grouped):
        print(f"  {group_name}:")
        for skill_name in grouped[group_name]:
            marker = "*" if skill_name in active_skills else " "
            print(f"    {marker} {skill_name}")


def _get_interface_name(cli_context: Dict[str, Any]) -> str:
    interface_name = cli_context.get("interface") if isinstance(cli_context, dict) else None
    return str(interface_name or "basic").strip().lower()


def _handle_interface_specific_command(command: str, interface_name: str) -> Optional[str]:
    if interface_name == "textual":
        print(f"{command} is available through the Textual UI command palette.")
        return None

    print(f"The {command} command is available only in the Textual UI.")
    print("Open the full interface to use Textual-only commands.")
    return None


def _handle_view_command(args: list[str], cli_context: Dict[str, Any], interface_name: str) -> Optional[str]:
    if interface_name != "textual":
        return _handle_interface_specific_command("/view", interface_name)

    open_picker = cli_context.get("textual_open_view_picker") if isinstance(cli_context, dict) else None
    set_view = cli_context.get("textual_set_view") if isinstance(cli_context, dict) else None
    get_view = cli_context.get("textual_get_current_view") if isinstance(cli_context, dict) else None

    if not args:
        if callable(open_picker):
            open_picker()
            print("Opened the view selector.")
        else:
            print("Textual view selector is unavailable.")
        return None

    subcommand = args[0].lower()
    current_view = str(get_view() or "") if callable(get_view) else ""

    if subcommand in {"list", "ls"}:
        print("Available views:")
        for view_name in TEXTUAL_VIEWS:
            marker = "*" if view_name == current_view else " "
            print(f"  {marker} {view_name}")
        return None

    if subcommand in {"show", "current"}:
        print(f"Current view: {current_view or 'unknown'}")
        return None

    target_view = args[1].lower() if subcommand in {"switch", "go"} and len(args) > 1 else subcommand
    if target_view not in TEXTUAL_VIEWS:
        print("Usage: /view [list|show|switch <chat|control|run>]")
        return None
    if not callable(set_view):
        print("Textual view switching is unavailable.")
        return None

    set_view(target_view, announce=True)
    print(f"View selected: {target_view}")
    return None


def list_command_suggestions(engine: PocketCodeEngine, interface_name: str | None = None) -> list[str]:
    flow_names = _list_flow_names(engine)
    agent_names = _list_agent_names(engine)
    suggestions = list(BASE_COMMAND_SUGGESTIONS)
    if str(interface_name or "").strip().lower() == "textual":
        suggestions += TEXTUAL_COMMAND_SUGGESTIONS
    provider_commands: list[str] = []
    if hasattr(engine, "get_command_providers"):
        for provider in engine.get_command_providers():
            try:
                provider_commands.extend(f"/{spec.name}" for spec in provider.list_commands(visibility="exported"))
            except Exception:
                continue
    return sorted(
        set(
            suggestions
            + flow_names
            + agent_names
            + (engine.list_skills() if hasattr(engine, "list_skills") else [])
            + engine.list_llm_profiles()
            + provider_commands
        )
    )


def handle_command(
    command_input: str,
    engine: PocketCodeEngine,
    cli_context: Dict[str, Any],
    active_run: Any = None,
) -> Optional[str]:
    try:
        parts = shlex.split(command_input.strip())
    except ValueError as exc:
        print(f"Command parse error: {exc}")
        return None
    if not parts:
        return None

    command = _normalize_command(parts[0].lower())
    args = parts[1:]
    interface_name = _get_interface_name(cli_context)

    if command == "/view":
        return _handle_view_command(args, cli_context, interface_name)

    if command in TEXTUAL_ONLY_COMMANDS:
        return _handle_interface_specific_command(command, interface_name)

    if command in {"/help"}:
        print_help(interface_name=interface_name)
        return None

    if command in {"/exit", "/quit"}:
        return "__exit__"

    if command in {"/reload"}:
        engine.reload()
        print("Reloaded resource roots, namespaces, agents, tools, skills, and LLM profile mappings.")
        return None

    if command == "/debug":
        return _handle_debug_command(args=args, cli_context=cli_context, interface_name=interface_name, active_run=active_run)

    if command in {"/stop", "/cancel"}:
        return _handle_stop_command(active_run)

    if command in {"/status"}:
        status = engine.status()
        run_summary = status.get("last_run_summary", {}) if isinstance(status, dict) else {}
        if not isinstance(run_summary, dict):
            run_summary = {}
        normalized_args = {str(arg).lower() for arg in args}
        verbose = bool({"verbose", "--verbose", "-v"} & normalized_args)
        show_steps = verbose or bool({"steps", "--steps", "timeline", "--timeline"} & normalized_args)
        print("Runtime status:")
        print(f"  Internal flow: {status.get('runtime_flow') or 'internal-flow'}")
        print(f"  Selected flow: {status.get('flow') or 'auto'}")
        print(f"  Agent: {status.get('agent') or 'none'}")
        print(f"  Skills: {status.get('skills') or []}")
        print(f"  Global LLM override: {status['global_llm_override']}")
        print(f"  Agent LLM overrides: {status['agent_llm_overrides']}")
        print(f"  Handoff LLM Overrides: {status.get('handoff_llm_overrides', {})}")
        print(f"  Config LLM Overrides: {status.get('config_llm_overrides', {})}")
        print(f"  Default LLM Profile: {status['default_llm_profile']}")
        print(f"  Tool Confirmation (config): {status.get('tool_confirmation', {})}")
        print(f"  Tool Confirmation (session overrides): {status.get('session_tool_confirmation_overrides', {})}")
        session_debugger_breakpoints = status.get("session_debugger_breakpoints", [])
        print(f"  Debugger Breakpoints (session): {len(session_debugger_breakpoints or [])}")
        print(f"  Runtime Events: {run_summary.get('runtime_event_count', 0)}")
        print(f"  Runtime Steps: {run_summary.get('step_count', 0)}")
        if verbose and session_debugger_breakpoints:
            for label in session_debugger_breakpoints:
                print(f"    - {label}")
        warning_codes = [
            str(item.get("code") or "").strip()
            for item in run_summary.get("vm_validation_warnings", [])
            if isinstance(item, dict) and str(item.get("code") or "").strip()
        ]
        if warning_codes:
            print(f"  VM Validation Warnings: {', '.join(warning_codes)}")
            if verbose:
                for item in run_summary.get("vm_validation_warnings", []):
                    if not isinstance(item, dict):
                        continue
                    code = str(item.get("code") or "").strip() or "warning"
                    message = str(item.get("message") or "").strip()
                    location = str(item.get("location") or "").strip()
                    if message:
                        prefix = f"{code} ({location})" if location else code
                        print(f"    - {prefix}: {message}")
        if show_steps:
            _print_run_steps(run_summary, verbose=verbose)
        return None

    if command in {"/flows", "/agents", "/prompts", "/skills", "/llms", "/tools", "/list"}:
        return _handle_list_command(command=command, args=args, engine=engine)

    if command in {
        "/flow",
        "/llm",
        "/llm-flow",
        "/llm-agent",
        "/llm-handoff",
        "/set",
    }:
        return _handle_set_command(command=command, args=args, engine=engine)

    if command == "/context":
        return _handle_context_command(args, cli_context)

    if command == "/confirm":
        return _handle_confirm_command(args, engine)

    if command == "/session":
        return _handle_session_command(args, engine)

    if command == "/stackvm":
        try:
            return handle_stackvm_command(args, engine)
        except Exception as exc:
            print(f"Error: {exc}")
            return None

    if command == "/agent":
        return _handle_agent_command(args, engine)

    if command == "/skill":
        return _handle_skill_command(args, engine)

    provider_result, provider_handled = _handle_provider_command(
        command=command,
        args=args,
        engine=engine,
        cli_context=cli_context,
    )
    if provider_handled:
        return provider_result

    print(f"Unknown command: {command}")
    print_help()
    return None


def _normalize_command(command: str) -> str:
    aliases = {
        "/q": "/quit",
        "/r": "/reload",
        "/c": "/cancel",
        "/st": "/status",
        "/ls": "/list",
        "/ag": "/agent",
        "/ap": "/agent",
        "/lm": "/llm",
        "/lf": "/llm-flow",
        "/la": "/llm-agent",
        "/lh": "/llm-handoff",
    }
    return aliases.get(command, command)


def _handle_debug_command(
    *,
    args: list[str],
    cli_context: Dict[str, Any],
    interface_name: str,
    active_run: Any,
) -> Optional[str]:
    if active_run is not None:
        print("A run is already active. Wait for it to finish or cancel it before starting the debugger.")
        return None

    if not args:
        print("Usage: /debug <request text>")
        return None

    runner = cli_context.get("debug_request_runner") if isinstance(cli_context, dict) else None
    if not callable(runner):
        print("The /debug command is not available in this interface.")
        return None

    request = " ".join(args).strip()
    if not request:
        print("Usage: /debug <request text>")
        return None

    try:
        result = runner(request)
    except Exception as exc:
        print(f"Error: {exc}")
        return None

    if result:
        print(result)
    return None


def _print_run_steps(run_summary: Dict[str, Any], *, verbose: bool) -> None:
    steps = run_summary.get("steps", [])
    if not isinstance(steps, list) or not steps:
        print("  Step Trace: (none)")
        return

    print("  Step Trace:")
    for step in steps:
        if not isinstance(step, dict):
            continue
        index = step.get("index")
        kind = str(step.get("kind") or "step")
        status = str(step.get("status") or "completed")
        summary = str(step.get("summary") or step.get("label") or kind)
        duration = step.get("duration_ms")
        duration_suffix = f" [{float(duration):.1f}ms]" if isinstance(duration, (int, float)) else ""
        print(f"    {index}. {kind} ({status}){duration_suffix} {summary}")
        if not verbose:
            continue
        details = step.get("details")
        if isinstance(details, dict) and details:
            print(f"       details: {details}")


def _handle_list_command(command: str, args: list[str], engine: PocketCodeEngine) -> Optional[str]:
    if command == "/flows":
        scope = "flows"
    elif command == "/prompts":
        scope = "prompts"
    elif command == "/agents":
        scope = "agents"
    elif command == "/skills":
        scope = "skills"
    elif command == "/llms":
        scope = "llms"
    elif command == "/tools":
        scope = "tools"
    else:
        if not args:
            print("Usage: /list <flows|prompts|skills|agents|llms|tools> [flow]")
            return None
        scope = args[0].lower()
        args = args[1:]

    if scope == "flows":
        flows = _list_flow_names(engine)
        current_flow = _get_current_flow_name(engine)
        print("Available flows:")
        for flow in flows:
            marker = "*" if flow == current_flow else " "
            print(f"  {marker} {flow}")
        return None

    if scope == "agents":
        agents = _list_user_agent_names(engine)
        active_agent = _get_active_agent_profile(engine)
        active_name = active_agent.name if active_agent else None
        print("Available agents:")
        for agent in agents:
            marker = "*" if agent == active_name else " "
            print(f"  {marker} {agent}")
        if not agents:
            print("  (none)")
        return None

    if scope == "skills":
        _print_grouped_skills(engine)
        return None

    if scope == "prompts":
        prompts = engine.list_prompts() if hasattr(engine, "list_prompts") else []
        print("Available prompts:")
        for prompt in prompts:
            print(f"    {prompt}")
        if not prompts:
            print("  (none)")
        return None

    if scope == "llms":
        profiles = engine.list_llm_profiles()
        print("Available LLM profiles:")
        for profile in profiles:
            marker = "*" if profile == engine.global_llm_override else " "
            print(f"  {marker} {profile}")
        print(f"Global override: {engine.global_llm_override or 'none'}")
        return None

    if scope == "tools":
        target_flow = args[0] if args else _get_current_flow_name(engine)
        if not target_flow:
            print("No active flow selected. Use /flow <name> or /tools <flow_name>.")
            return None
        try:
            tool_descriptions = (
                engine.describe_tools_for_flow(target_flow)
                if hasattr(engine, "describe_tools_for_flow")
                else engine.describe_tools_for_agent(target_flow)
            )
        except Exception as exc:
            print(f"Error: {exc}")
            return None

        print(f"Tools for flow '{target_flow}':")
        for tool in tool_descriptions:
            print(f"  - {tool['name']}: {tool.get('description', '')}")
        return None

    print(f"Unknown list scope: {scope}")
    print("Usage: /list <flows|prompts|skills|agents|llms|tools> [flow]")
    return None


def _handle_set_command(command: str, args: list[str], engine: PocketCodeEngine) -> Optional[str]:
    if command == "/set":
        if not args:
            print(
                "Usage: /set <flow|llm|llm-flow|llm-handoff> <args...>"
            )
            return None
        command = f"/{args[0].lower()}"
        args = args[1:]
        if command == "/llm-agent":
            command = "/llm-flow"

    if command == "/flow":
        if not args:
            current_flow = _get_current_flow_name(engine)
            current_agent = _get_active_agent_profile(engine)
            print(f"Current flow: {current_flow or 'auto'}")
            if current_agent:
                print(f"Current agent: {current_agent.name}")
            print("Usage: /flow <flow_name|auto> [--agent <agent_name>]")
            return None
        target, selected_agent = _parse_agent_selection_flag(args)
        try:
            if target.lower() == "auto":
                if hasattr(engine, "set_flow"):
                    engine.set_flow(None)
                else:
                    engine.set_agent(None)
                print("Flow selection reset to runtime default/handoff.")
            else:
                if hasattr(engine, "set_flow"):
                    engine.set_flow(target)
                else:
                    engine.set_agent(target)
                print(f"Selected flow: {target}")
            if selected_agent is not None:
                try:
                    if hasattr(engine, "set_active_agent"):
                        engine.set_active_agent(selected_agent)
                    else:
                        engine.set_active_agent_profile(selected_agent)
                    print(f"Agent activated: {selected_agent}")
                except ValueError as exc:
                    print(f"Warning: {exc}")
        except Exception as exc:
            print(f"Error: {exc}")
        return None

    if command == "/llm":
        if not args:
            print(f"Current global LLM override: {engine.global_llm_override or 'none'}")
            print("Usage: /llm <profile_name|none>")
            return None
        selected = args[0]
        try:
            if selected.lower() in {"none", "reset", "auto"}:
                engine.set_global_llm_override(None)
                print("Global LLM override cleared.")
            else:
                engine.set_global_llm_override(selected)
                print(f"Global LLM override set to: {selected}")
        except Exception as exc:
            print(f"Error: {exc}")
        return None

    if command in {"/llm-flow", "/llm-agent"}:
        if len(args) < 2:
            print("Usage: /llm-flow <flow_name> <profile_name|none>")
            return None
        flow_name, profile_name = args[0], args[1]
        try:
            if profile_name.lower() in {"none", "reset", "auto"}:
                if hasattr(engine, "set_flow_llm_override"):
                    engine.set_flow_llm_override(flow_name, None)
                else:
                    engine.set_agent_llm_override(flow_name, None)
                print(f"Flow-specific LLM override cleared for: {flow_name}")
            else:
                if hasattr(engine, "set_flow_llm_override"):
                    engine.set_flow_llm_override(flow_name, profile_name)
                else:
                    engine.set_agent_llm_override(flow_name, profile_name)
                print(f"Flow-specific LLM override set: {flow_name} -> {profile_name}")
        except Exception as exc:
            print(f"Error: {exc}")
        return None

    if command == "/llm-handoff":
        if len(args) < 3:
            print("Usage: /llm-handoff <source_agent> <target_agent> <profile_name|none>")
            return None
        source_agent, target_agent, profile_name = args[0], args[1], args[2]
        try:
            if profile_name.lower() in {"none", "reset", "auto"}:
                engine.set_handoff_llm_override(
                    source_agent=source_agent,
                    target_agent=target_agent,
                    profile_name=None,
                )
                print(f"Handoff-specific LLM override cleared: {source_agent}->{target_agent}")
            else:
                engine.set_handoff_llm_override(
                    source_agent=source_agent,
                    target_agent=target_agent,
                    profile_name=profile_name,
                )
                print(
                    f"Handoff-specific LLM override set: "
                    f"{source_agent}->{target_agent} -> {profile_name}"
                )
        except Exception as exc:
            print(f"Error: {exc}")
        return None

    print(f"Unknown set target: {command}")
    print("Usage: /set <flow|llm|llm-flow|llm-handoff> <args...>")
    return None


def _handle_context_command(args: list[str], cli_context: Dict[str, Any]) -> Optional[str]:
    if not args:
        print("Usage: /context <show|add|remove|clear|help> [options]")
        return None

    subcommand = args[0].lower()
    sub_args = args[1:]

    if subcommand == "help":
        print_context_help()
        return None

    if subcommand == "show":
        show_type = sub_args[0].lower() if sub_args else "all"
        print("--- Current CLI Context ---")
        if show_type in {"all", "files"} and cli_context.get("files"):
            print("Files:")
            for item in sorted(list(cli_context["files"])):
                print(f"  - {item}")
        if show_type in {"all", "folders"} and cli_context.get("folders"):
            print("Folders:")
            for item in sorted(list(cli_context["folders"])):
                print(f"  - {item}")
        if show_type in {"all", "urls"} and cli_context.get("urls"):
            print("URLs:")
            for item in sorted(list(cli_context["urls"])):
                print(f"  - {item}")
        if show_type in {"all", "snippets"} and cli_context.get("snippets"):
            print("Snippets:")
            for name, content in sorted(cli_context["snippets"].items()):
                print(f"  - {name}: {content[:120]}{'...' if len(content) > 120 else ''}")
        if not cli_context.get("files") and not cli_context.get("folders") and not cli_context.get("urls") and not cli_context.get("snippets"):
            print("(Context is empty)")
        print("---------------------------")
        return None

    if subcommand == "add":
        if len(sub_args) < 2:
            print("Usage: /context add <file|folder|url|snippet> <value...>")
            return None

        add_type = sub_args[0].lower()
        value = sub_args[1:]

        if add_type == "file":
            cli_context["files"].add(value[0])
            print(f"Added file context: {value[0]}")
            return None

        if add_type == "folder":
            cli_context["folders"].add(value[0])
            print(f"Added folder context: {value[0]}")
            return None

        if add_type == "url":
            cli_context["urls"].add(value[0])
            print(f"Added URL context: {value[0]}")
            return None

        if add_type == "snippet":
            if len(value) < 2:
                print("Usage: /context add snippet <name> <content...>")
                return None
            snippet_name = value[0]
            snippet_content = " ".join(value[1:])
            cli_context["snippets"][snippet_name] = snippet_content
            print(f"Added snippet context: {snippet_name}")
            return None

        print(f"Unknown context type to add: {add_type}")
        return None

    if subcommand == "remove":
        if len(sub_args) < 2:
            print("Usage: /context remove <file|folder|url|snippet> <value>")
            return None

        remove_type = sub_args[0].lower()
        identifier = sub_args[1]

        if remove_type == "file":
            removed = identifier in cli_context["files"]
            cli_context["files"].discard(identifier)
        elif remove_type == "folder":
            removed = identifier in cli_context["folders"]
            cli_context["folders"].discard(identifier)
        elif remove_type == "url":
            removed = identifier in cli_context["urls"]
            cli_context["urls"].discard(identifier)
        elif remove_type == "snippet":
            removed = identifier in cli_context["snippets"]
            cli_context["snippets"].pop(identifier, None)
        else:
            print(f"Unknown context type to remove: {remove_type}")
            return None

        if removed:
            print(f"Removed {remove_type} context: {identifier}")
        else:
            print(f"{remove_type.capitalize()} context not found: {identifier}")
        return None

    if subcommand == "clear":
        clear_type = sub_args[0].lower() if sub_args else "all"

        if clear_type in {"all", "files"}:
            cli_context["files"].clear()
        if clear_type in {"all", "folders"}:
            cli_context["folders"].clear()
        if clear_type in {"all", "urls"}:
            cli_context["urls"].clear()
        if clear_type in {"all", "snippets"}:
            cli_context["snippets"].clear()

        if clear_type not in {"all", "files", "folders", "urls", "snippets"}:
            print(f"Unknown context type to clear: {clear_type}")
        else:
            print(f"Cleared context: {clear_type}")
        return None

    print(f"Unknown /context subcommand: {subcommand}")
    return None


def _handle_stop_command(active_run: Any) -> Optional[str]:
    if active_run is None:
        print("No run is currently active.")
        return None

    cancel = getattr(active_run, "cancel", None)
    if not callable(cancel):
        print("Active run does not support cancellation.")
        return None

    if cancel("Run cancelled from CLI."):
        print("Stop requested for the active run.")
    else:
        print("The active run is already stopping or has completed.")
    return None


def _handle_provider_command(
    *,
    command: str,
    args: list[str],
    engine: PocketCodeEngine,
    cli_context: Dict[str, Any],
) -> tuple[Optional[str], bool]:
    if not hasattr(engine, "invoke_registered_command"):
        return None, False
    try:
        result = engine.invoke_registered_command(command, args, cli_context=cli_context)
    except PermissionError as exc:
        print(f"Permission denied: {exc}")
        return None, True
    except Exception as exc:
        print(f"Error: {exc}")
        return None, True
    if not isinstance(result, CommandResult) or not result.handled:
        return None, False
    if result.output:
        print(result.output)
    if result.exit_requested:
        return "__exit__", True
    return None, True


def _handle_skill_command(
    args: list[str],
    engine: PocketCodeEngine,
) -> Optional[str]:
    if not args:
        print_skill_help()
        return None

    subcommand = args[0].lower()
    sub_args = args[1:]

    if subcommand == "help":
        print_skill_help()
        return None

    if subcommand == "list":
        _print_grouped_skills(engine)
        return None

    if subcommand == "show":
        if not sub_args:
            print("Usage: /skill show <skill_name>")
            return None
        skill = engine.get_skill(sub_args[0]) if hasattr(engine, "get_skill") else None
        if skill is None:
            print(f"Skill not found: {sub_args[0]}")
            return None
        print(f"Skill: {skill.name}")
        print(f"  Desc     : {skill.description or '-'}")
        print(f"  Tools    : {skill.tool_refs or []}")
        print(f"  Provided : {sorted(skill.provided_tools.keys())}")
        print(f"  Extra    : {skill.extra_prompts or []}")
        print(f"  Refs     : {skill.references or []}")
        print(f"  Scripts  : {skill.scripts or []}")
        print(f"  Assets   : {skill.assets or []}")
        if getattr(skill, "source_path", None):
            print(f"  Path     : {skill.source_path}")
        return None

    if subcommand in {"enable", "disable"}:
        print(
            "Skill mutation commands were removed from the CLI. "
            "Use ACP/provider commands or configure them through the active agent/runtime."
        )
        return None

    print(f"Unknown /skill subcommand: {subcommand}")
    print_skill_help()
    return None


def print_help(interface_name: str | None = None) -> None:
    help_text = """
Pocketcode Commands:
  /help                          Show this help message.
  /list <scope> [opts]           List entities by scope.
                                 Scopes: flows|prompts|skills|agents|llms|tools [flow for tools]
  /set <target> <args...>        Set runtime selection/override.
                                 Targets: flow|llm|llm-flow|llm-handoff
  /flow <flow_name|auto>         Select the active flow.
                                 Optional: --agent <agent_name>
  /debug <request text>          Run one request under the interactive debugger.
  /prompts                       List registered prompts.
  /skill <cmd> [opts]            Inspect runtime skills. Run '/skill help'.
  /reload                        Reload resource roots and runtime catalogs.
  /stop, /cancel                 Request cancellation of the active run.
  /status [verbose|steps]        Show runtime status and optional step trace.
  /context <cmd> [opts]          Manage context. Run '/context help'.
    /confirm <cmd> [opts]          Manage tool confirmation policies. Run '/confirm help'.
    /session <cmd> [opts]          Manage saved sessions. Run '/session help'.
  /agent <cmd> [opts]            Inspect or switch agents. Run '/agent help'.
  /stackvm <cmd> [opts]          Manage StackVM flows, scripts, and agents. Run '/stackvm help'.
  /exit, /quit                   Exit Pocketcode.

Compatibility aliases:
  /flows     -> /list flows
  /prompts   -> /list prompts
  /skills    -> /list skills
  /agents    -> /list agents
  /llms      -> /list llms
  /tools     -> /list tools
  /llm       -> /set llm
  /llm-flow  -> /set llm-flow
  /llm-agent -> /set llm-flow
  /llm-handoff -> /set llm-handoff

Shortcut aliases:
  /ls   /list
  /ag   /agent
  /ap   /agent
  /lm   /llm
  /lf   /llm-flow
  /la   /llm-flow
  /lh   /llm-handoff
  /st   /status
    /c    /cancel
  /r    /reload
  /q    /quit
"""
    print(help_text)

    if interface_name == "textual":
        textual_help = """
Textual-only commands:
  /copy                         Copy last assistant response.
  /copy-all                     Copy full response console output.
  /view [cmd]                   Open or control the Textual view selector.

Textual UI shortcuts:
  Tab                           Complete current prompt input.
  F2                            Open previous main-input entries and load one back into the prompt.
  F5                            Open the global view selector (Chat, Control, Run).
  F3                            Open the popup edit selector (agent, LLM, tools, tool policies, flow assets, tool assets).
  F4                            Open the popup clone selector (agent, LLM, flow assets, tool assets).
  F6                            Open the Control Center (agent, LLM, skills, tools, policies, presets, confirm, system settings).
  Ctrl+P / Ctrl+N               Cycle backward or forward through previous main-input entries.
  F10                           Toggle the right inspector panel.
  Ctrl+Shift+A                  Copy full response console output.
  Ctrl+Y                        Copy last assistant response.
  Ctrl+Q                        Quit Textual UI.
"""
        print(textual_help)


def print_context_help() -> None:
    context_help = """
/context Commands:
  /context show [files|folders|urls|snippets|all]
  /context add file <path>
  /context add folder <path>
  /context add url <url>
  /context add snippet <name> <content...>
  /context remove file <path>
  /context remove folder <path>
  /context remove url <url>
  /context remove snippet <name>
  /context clear [files|folders|urls|snippets|all]
  /context help
"""
    print(context_help)


print_stackvm_command_help = print_stackvm_help


def _handle_confirm_command(args: list[str], engine: PocketCodeEngine) -> Optional[str]:
    if not args:
        print("Usage: /confirm <show|session|tool|agent|agent-tool|clear|help> ...")
        return None

    subcommand = args[0].lower()
    sub_args = args[1:]

    if subcommand == "help":
        print_confirm_help()
        return None

    if subcommand == "show":
        status = engine.status()
        print("Tool confirmation configuration:")
        print(f"  Config: {status.get('tool_confirmation', {})}")
        print(f"  Session overrides: {status.get('session_tool_confirmation_overrides', {})}")
        return None

    if subcommand == "clear":
        engine.clear_session_confirmation_overrides()
        print("Cleared all session-level tool confirmation overrides.")
        return None

    if subcommand == "session":
        if len(sub_args) != 1:
            print("Usage: /confirm session <allow|confirm|deny|reset>")
            return None
        policy = _parse_policy_or_reset(sub_args[0])
        try:
            engine.set_session_confirmation_default(policy)
            print(f"Session default confirmation policy set to: {policy or 'reset'}")
        except Exception as exc:
            print(f"Error: {exc}")
        return None

    if subcommand == "tool":
        if len(sub_args) != 2:
            print("Usage: /confirm tool <tool_name> <allow|confirm|deny|reset>")
            return None
        tool_name = sub_args[0]
        policy = _parse_policy_or_reset(sub_args[1])
        try:
            engine.set_session_tool_confirmation(tool_name, policy)
            print(f"Session tool policy set: {tool_name} -> {policy or 'reset'}")
        except Exception as exc:
            print(f"Error: {exc}")
        return None

    if subcommand == "agent":
        if len(sub_args) != 2:
            print("Usage: /confirm agent <agent_name> <allow|confirm|deny|reset>")
            return None
        agent_name = sub_args[0]
        policy = _parse_policy_or_reset(sub_args[1])
        try:
            engine.set_session_agent_confirmation(agent_name, policy)
            print(f"Session agent policy set: {agent_name} -> {policy or 'reset'}")
        except Exception as exc:
            print(f"Error: {exc}")
        return None

    if subcommand == "agent-tool":
        if len(sub_args) != 3:
            print("Usage: /confirm agent-tool <agent_name> <tool_name> <allow|confirm|deny|reset>")
            return None
        agent_name = sub_args[0]
        tool_name = sub_args[1]
        policy = _parse_policy_or_reset(sub_args[2])
        try:
            engine.set_session_agent_tool_confirmation(agent_name, tool_name, policy)
            print(f"Session agent tool policy set: {agent_name}.{tool_name} -> {policy or 'reset'}")
        except Exception as exc:
            print(f"Error: {exc}")
        return None

    print(f"Unknown /confirm subcommand: {subcommand}")
    print_confirm_help()
    return None


def _parse_policy_or_reset(raw: str) -> str | None:
    lowered = raw.strip().lower()
    if lowered in {"reset", "none", "default"}:
        return None
    return lowered


def print_confirm_help() -> None:
    confirm_help = """
/confirm Commands:
  /confirm show
  /confirm clear
  /confirm session <allow|confirm|deny|reset>
  /confirm tool <tool_name> <allow|confirm|deny|reset>
  /confirm agent <agent_name> <allow|confirm|deny|reset>
  /confirm agent-tool <agent_name> <tool_name> <allow|confirm|deny|reset>
  /confirm help
"""
    print(confirm_help)


def _handle_session_command(args: list[str], engine: PocketCodeEngine) -> Optional[str]:
    if not args:
        print("Usage: /session <show|list|new|resume|delete|clear-all|clear-breakpoints|help> ...")
        return None

    subcommand = args[0].lower()
    sub_args = args[1:]

    if subcommand == "help":
        print_session_help()
        return None

    if subcommand == "show":
        target_id = sub_args[0] if sub_args else None
        session = (
            engine.get_saved_session_details(target_id)
            if hasattr(engine, "get_saved_session_details")
            else (engine.get_active_session_info() if hasattr(engine, "get_active_session_info") else {})
        )
        if not session or not session.get("session_id"):
            print("No active session.")
            return None
        print("Session:")
        print(f"  Id: {session.get('session_id')}")
        print(f"  Title: {session.get('title') or '-'}")
        print(f"  Updated: {session.get('updated_at') or '-'}")
        if "loaded_from_history" in session:
            print(f"  Resumed: {'yes' if session.get('loaded_from_history') else 'no'}")
        print(f"  Debugger Breakpoints: {session.get('debugger_breakpoint_count', 0)}")
        for label in session.get("debugger_breakpoints", []) or []:
            print(f"    - {label}")
        return None

    if subcommand == "list":
        sessions = engine.list_saved_sessions() if hasattr(engine, "list_saved_sessions") else []
        print("Saved sessions:")
        if not sessions:
            print("  (none)")
            return None
        for item in sessions:
            marker = "*" if item.get("is_active") else " "
            updated_at = item.get("updated_at") or "-"
            print(
                f"  {marker} {item.get('session_id')} | {item.get('title') or '-'} | "
                f"{updated_at} | breaks={item.get('debugger_breakpoint_count', 0)}"
            )
        return None

    if subcommand == "new":
        title = " ".join(sub_args).strip() or None
        session = {}
        if hasattr(engine, "start_new_session"):
            session = engine.start_new_session(title) if title else engine.start_new_session()
        print(f"Started new session: {session.get('session_id')}")
        if session.get("title"):
            print(f"  Title: {session.get('title')}")
        return None

    if subcommand == "resume":
        if len(sub_args) != 1:
            print("Usage: /session resume <session_id>")
            return None
        try:
            session = engine.resume_session(sub_args[0]) if hasattr(engine, "resume_session") else {}
        except Exception as exc:
            print(f"Error: {exc}")
            return None
        print(f"Resumed session: {session.get('session_id')}")
        if session.get("title"):
            print(f"  Title: {session.get('title')}")
        return None

    if subcommand == "delete":
        if not sub_args:
            print("Usage: /session delete <session_id> --yes")
            return None
        if "--yes" not in sub_args:
            print("Deleting a session requires --yes.")
            return None
        session_id = next((arg for arg in sub_args if arg != "--yes"), "")
        if not session_id:
            print("Usage: /session delete <session_id> --yes")
            return None
        try:
            deleted = engine.delete_session(session_id) if hasattr(engine, "delete_session") else {}
        except Exception as exc:
            print(f"Error: {exc}")
            return None
        print(f"Deleted session: {deleted.get('session_id')}")
        return None

    if subcommand == "clear-all":
        if "--yes" not in sub_args:
            print("Clearing saved sessions requires --yes.")
            return None
        try:
            removed = engine.clear_saved_sessions() if hasattr(engine, "clear_saved_sessions") else 0
        except Exception as exc:
            print(f"Error: {exc}")
            return None
        print(f"Cleared {removed} saved session{'s' if removed != 1 else ''}.")
        return None

    if subcommand == "clear-breakpoints":
        if not sub_args:
            print("Usage: /session clear-breakpoints <session_id> --yes")
            return None
        if "--yes" not in sub_args:
            print("Clearing saved debugger breakpoints requires --yes.")
            return None
        session_id = next((arg for arg in sub_args if arg != "--yes"), "")
        if not session_id:
            print("Usage: /session clear-breakpoints <session_id> --yes")
            return None
        try:
            cleared = (
                engine.clear_saved_session_debugger_breakpoints(session_id)
                if hasattr(engine, "clear_saved_session_debugger_breakpoints")
                else {}
            )
        except Exception as exc:
            print(f"Error: {exc}")
            return None
        print(
            f"Cleared {cleared.get('cleared', 0)} debugger breakpoint(s) from session: "
            f"{cleared.get('session_id')}"
        )
        return None

    print(f"Unknown /session subcommand: {subcommand}")
    print_session_help()
    return None


def print_session_help() -> None:
    session_help = """
/session Commands:
  /session show
  /session show <session_id>
  /session list
  /session new [title...]
  /session resume <session_id>
  /session delete <session_id> --yes
  /session clear-all --yes
  /session clear-breakpoints <session_id> --yes
  /session help
"""
    print(session_help)


def _parse_agent_selection_flag(args: list[str]) -> tuple[str, str | None]:
    """Extract ``--agent <name>`` from *args*.

    Returns ``(positional_target, agent_name)`` where *positional_target* is the
    first non-flag argument and *agent_name* is the value following the agent
    selection flag, if supplied.
    """
    agent_name: str | None = None
    cleaned: list[str] = []
    i = 0
    while i < len(args):
        if args[i] in {"--agent", "--profile", "--agent-profile"} and i + 1 < len(args):
            agent_name = args[i + 1]
            i += 2
        else:
            cleaned.append(args[i])
            i += 1
    return (cleaned[0] if cleaned else ""), agent_name


def _handle_agent_command(
    args: list[str],
    engine: PocketCodeEngine,
) -> Optional[str]:
    """Dispatch /agent sub-commands."""
    if not args:
        print_agent_help()
        return None

    subcommand = args[0].lower()
    sub_args = args[1:]

    if subcommand == "help":
        print_agent_help()
        return None

    if subcommand == "list":
        agents = _list_user_agent_names(engine)
        if not agents:
            print("No agents available.")
            return None
        active = _get_active_agent_profile(engine)
        print("Available agents:")
        for name in agents:
            marker = "*" if (active and active.name == name) else " "
            print(f"  {marker} {name}")
        return None

    if subcommand == "show":
        if sub_args:
            profile = engine.get_agent(sub_args[0]) if hasattr(engine, "get_agent") else engine.get_agent_profile(sub_args[0])
            if profile is None:
                print(f"Agent not found: {sub_args[0]}")
                return None
        else:
            profile = engine.get_agent() if hasattr(engine, "get_agent") else engine.get_agent_profile()
            if not profile:
                print("No agent is currently active.")
                return None
        print(f"Agent: {profile.name}")
        print(f"  Flow     : {profile.agent}")
        print(f"  Desc     : {profile.description or '\u2014'}")
        print(f"  LLM      : {profile.llm_profile or '(inherit)'}")
        print(f"  Tools    : {', '.join(profile.tools) if profile.tools is not None else '(all)'}")
        print(f"  Extra    : {profile.extra_prompts or []}")
        print(f"  Confirm  : {profile.tool_confirmation or {}}")
        print(f"  Source   : {profile.source}")
        if profile.source_path:
            print(f"  Path     : {profile.source_path}")
        return None

    if subcommand == "switch":
        if not sub_args:
            print("Usage: /agent switch <agent_name>")
            return None
        name = sub_args[0]
        try:
            if hasattr(engine, "set_active_agent"):
                engine.set_active_agent(name)
            else:
                engine.set_active_agent_profile(name)
            print(f"Agent activated: {name}")
        except ValueError as exc:
            print(f"Error: {exc}")
        return None

    if subcommand in {"clone", "new", "edit", "tools", "policy"}:
        print(
            "Agent mutation commands were removed from the CLI. "
            "Use ACP/provider commands or edit workspace files directly."
        )
        return None

    print(f"Unknown /agent subcommand: {subcommand}")
    print_agent_help()
    return None




def print_agent_help() -> None:
    text = """
/agent Commands:
  /agent list                                 List all named agents (excludes synthesised flow defaults).
  /agent show [agent_name]                    Show details of an agent (default: active).
  /agent switch <agent_name>                  Activate an agent.
  /agent help                                 Show this help message.

Usage with /flow:
  /flow <flow_name> [--agent <agent_name>]

Notes:
  Agent mutation commands are no longer exposed through the CLI.
  Use ACP/provider commands or edit workspace files directly.

Compatibility:
    Agent shortcuts only: /ag and /ap map to /agent.
"""
    print(text)


def print_skill_help() -> None:
    text = """
/skill Commands:
  /skill list                                List all available skills grouped by top-level name prefix.
  /skill show <skill_name>                   Show details of a skill.
  /skill help                                Show this help message.
"""
    print(text)


_parse_agent_profile_flag = _parse_agent_selection_flag
_handle_agent_profile_command = _handle_agent_command
print_agent_profile_help = print_agent_help
