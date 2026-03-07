from __future__ import annotations

import logging
import shlex
from typing import Any, Dict, Optional

from pocketcode.core.engine import PocketCodeEngine

logger = logging.getLogger(__name__)

BASE_COMMAND_SUGGESTIONS = [
    "/help",
    "/list",
    "/set",
    "/flows",
    "/flow",
    "/prompts",
    "/modes",
    "/mode",
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
    "/stop",
    "/cancel",
    "/status",
    "/context",
    "/confirm",
    "/agent list",
    "/agent show",
    "/agent switch",
    "/agent clone",
    "/agent edit",
    "/agent edit llm",
    "/agent edit prompts",
    "/agent tools",
    "/agent policy",
    "/mode list",
    "/mode show",
    "/mode switch",
    "/mode clear",
    "/skill list",
    "/skill show",
    "/skill enable",
    "/skill disable",
    "/copy",
    "/copy-all",
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
    if "::" in cleaned:
        return cleaned.split("::", 1)[0]
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


def list_command_suggestions(engine: PocketCodeEngine) -> list[str]:
    flow_names = _list_flow_names(engine)
    agent_names = _list_agent_names(engine)
    return sorted(
        set(
            BASE_COMMAND_SUGGESTIONS
            + flow_names
            + agent_names
            + (engine.list_modes() if hasattr(engine, "list_modes") else [])
            + (engine.list_skills() if hasattr(engine, "list_skills") else [])
            + engine.list_llm_profiles()
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

    if command in {"/help"}:
        print_help()
        return None

    if command in {"/exit", "/quit"}:
        return "__exit__"

    if command in {"/reload"}:
        engine.reload()
        print("Reloaded plugins, agents, tools, and LLM profile mappings.")
        return None

    if command in {"/stop", "/cancel"}:
        return _handle_stop_command(active_run)

    if command in {"/status"}:
        status = engine.status()
        print("Runtime status:")
        print(f"  Flow: {status.get('flow')}")
        print(f"  Agent: {status.get('agent')}")
        print(f"  Mode: {status.get('mode')}")
        print(f"  Skills: {status.get('skills')}")
        print(f"  Global LLM Override: {status['global_llm_override']}")
        print(f"  Agent LLM Overrides: {status['agent_llm_overrides']}")
        print(f"  Handoff LLM Overrides: {status.get('handoff_llm_overrides', {})}")
        print(f"  Config LLM Overrides: {status.get('config_llm_overrides', {})}")
        print(f"  Default LLM Profile: {status['default_llm_profile']}")
        print(f"  Tool Confirmation (config): {status.get('tool_confirmation', {})}")
        print(f"  Tool Confirmation (session overrides): {status.get('session_tool_confirmation_overrides', {})}")
        return None

    if command in {"/flows", "/agents", "/prompts", "/modes", "/skills", "/llms", "/tools", "/list"}:
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

    if command == "/agent":
        return _handle_agent_command(args, engine)

    if command == "/mode":
        return _handle_mode_command(args, engine)

    if command == "/skill":
        return _handle_skill_command(args, engine)

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


def _handle_list_command(command: str, args: list[str], engine: PocketCodeEngine) -> Optional[str]:
    if command == "/flows":
        scope = "flows"
    elif command == "/prompts":
        scope = "prompts"
    elif command == "/agents":
        scope = "agents"
    elif command == "/modes":
        scope = "modes"
    elif command == "/skills":
        scope = "skills"
    elif command == "/llms":
        scope = "llms"
    elif command == "/tools":
        scope = "tools"
    else:
        if not args:
            print("Usage: /list <flows|prompts|modes|skills|agents|llms|tools> [flow]")
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

    if scope == "modes":
        modes = engine.list_modes() if hasattr(engine, "list_modes") else []
        active_mode = engine.get_mode() if hasattr(engine, "get_mode") else None
        print("Available modes:")
        for mode in modes:
            marker = "*" if active_mode and active_mode.name == mode else " "
            print(f"  {marker} {mode}")
        if not modes:
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
    print("Usage: /list <flows|prompts|agents|llms|tools> [flow]")
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


def _handle_mode_command(
    args: list[str],
    engine: PocketCodeEngine,
) -> Optional[str]:
    if not args:
        print_mode_help()
        return None

    subcommand = args[0].lower()
    sub_args = args[1:]

    if subcommand == "help":
        print_mode_help()
        return None

    if subcommand == "list":
        modes = engine.list_modes() if hasattr(engine, "list_modes") else []
        active_mode = engine.get_mode() if hasattr(engine, "get_mode") else None
        print("Available modes:")
        for name in modes:
            marker = "*" if active_mode and active_mode.name == name else " "
            print(f"  {marker} {name}")
        if not modes:
            print("  (none)")
        return None

    if subcommand == "show":
        mode = None
        if sub_args and hasattr(engine, "get_mode"):
            mode = engine.get_mode(sub_args[0])
        elif hasattr(engine, "get_mode"):
            mode = engine.get_mode()
        if mode is None:
            print("No mode is currently active." if not sub_args else f"Mode not found: {sub_args[0]}")
            return None
        print(f"Mode: {mode.name}")
        print(f"  Desc     : {mode.description or '-'}")
        print(f"  Flow     : {mode.flow or '(inherit)'}")
        print(f"  Agent    : {mode.agent or '(inherit)'}")
        print(f"  LLM      : {mode.llm_profile or '(inherit)'}")
        print(f"  Tools    : {mode.tools if mode.tools_specified else '(inherit)'}")
        print(f"  Extra    : {mode.extra_prompts or []}")
        print(f"  Confirm  : {mode.tool_confirmation or {}}")
        if getattr(mode, "source_path", None):
            print(f"  Path     : {mode.source_path}")
        return None

    if subcommand == "switch":
        if not sub_args:
            print("Usage: /mode switch <mode_name>")
            return None
        try:
            engine.set_mode(sub_args[0])
            print(f"Mode activated: {sub_args[0]}")
        except ValueError as exc:
            print(f"Error: {exc}")
        return None

    if subcommand in {"clear", "reset", "off"}:
        engine.set_mode(None)
        print("Mode cleared.")
        return None

    print(f"Unknown /mode subcommand: {subcommand}")
    print_mode_help()
    return None


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

    if subcommand == "enable":
        if not sub_args:
            print("Usage: /skill enable <skill_name>")
            return None
        try:
            engine.enable_skill(sub_args[0])
            print(f"Skill enabled: {sub_args[0]}")
        except ValueError as exc:
            print(f"Error: {exc}")
        return None

    if subcommand == "disable":
        if not sub_args:
            print("Usage: /skill disable <skill_name>")
            return None
        engine.disable_skill(sub_args[0])
        print(f"Skill disabled: {sub_args[0]}")
        return None

    print(f"Unknown /skill subcommand: {subcommand}")
    print_skill_help()
    return None


def print_help() -> None:
    help_text = """
Pocketcode Commands:
  /help                          Show this help message.
  /list <scope> [opts]           List entities by scope.
                                 Scopes: flows|prompts|modes|skills|agents|llms|tools [flow for tools]
  /set <target> <args...>        Set runtime selection/override.
                                 Targets: flow|llm|llm-flow|llm-handoff
  /flow <flow_name|auto>         Select the active flow.
                                 Optional: --agent <agent_name>
  /prompts                       List registered prompts.
  /mode <cmd> [opts]             Manage runtime modes. Run '/mode help'.
  /skill <cmd> [opts]            Manage runtime skills. Run '/skill help'.
  /reload                        Reload plugins and runtime catalogs.
  /stop, /cancel                 Request cancellation of the active run.
  /status                        Show runtime status.
  /context <cmd> [opts]          Manage context. Run '/context help'.
  /confirm <cmd> [opts]          Manage tool confirmation policies. Run '/confirm help'.
  /agent <cmd> [opts]            Manage agents. Run '/agent help'.
  /copy, /copy-all               Copy response text (Textual UI).
  /exit, /quit                   Exit Pocketcode.

Compatibility aliases:
  /flows     -> /list flows
  /prompts   -> /list prompts
  /modes     -> /list modes
  /skills    -> /list skills
  /agents    -> /list agents
  /llms      -> /list llms
  /tools     -> /list tools
  /llm       -> /set llm
  /llm-flow  -> /set llm-flow
  /llm-agent -> /set llm-flow
  /llm-handoff -> /set llm-handoff

Keyboard shortcuts (Textual UI):
  Tab                           Complete current prompt input.
  F1 / F2 / F5                  Switch Chat / Control / Run views.
  F3                            Open the popup editor selector (agent, LLM, tools, tool policies).
  F4                            Open the popup clone selector (agent, LLM).
  F6                            Open Select (agent, LLM, skills, tools, tool policies, confirm, system settings).
  F10                           Toggle the right inspector panel.
  Alt+1 / Alt+2 / Alt+5         Switch Chat / Control / Run views.
  Ctrl+Shift+A                  Copy full response console output.
  Ctrl+Y                        Copy last assistant response.
  Ctrl+Q                        Quit Textual UI.

Textual convenience commands:
  /copy                         Copy last assistant response.
  /copy-all                     Copy full response console output.

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

    if subcommand == "clone":
        if len(sub_args) < 2:
            print("Usage: /agent clone <source_agent> <new_agent_name>")
            return None
        src, new_name = sub_args[0], sub_args[1]
        try:
            cloner = engine.clone_agent if hasattr(engine, "clone_agent") else engine.clone_agent_profile
            cloned = cloner(src, new_name)
            target_path = getattr(cloned, "source_path", None)
            if target_path:
                print(f"Cloned agent '{src}' \u2192 '{new_name}' at {target_path}.")
            else:
                print(f"Cloned agent '{src}' \u2192 '{new_name}'.")
        except (KeyError, ValueError) as exc:
            print(f"Error: {exc}")
        return None

    if subcommand == "edit":
        return _handle_agent_edit_command(sub_args, engine)

    if subcommand == "tools":
        return _handle_agent_tools_command(sub_args, engine)

    if subcommand == "policy":
        return _handle_agent_policy_command(sub_args, engine)

    print(f"Unknown /agent subcommand: {subcommand}")
    print_agent_help()
    return None


def _handle_agent_tools_command(
    args: list[str],
    engine: PocketCodeEngine,
) -> Optional[str]:
    if len(args) < 2:
        print("Usage: /agent tools <agent_name> <all|none|set> [tool_name ...]")
        return None

    profile_name = args[0]
    action = args[1].lower()
    profile = _get_editable_agent_profile(engine, profile_name)
    if profile is None:
        return None

    available_tools = set(engine.list_tools_for_agent(profile.agent))
    updated_tools: list[str] | None
    if action == "all":
        updated_tools = None
    elif action == "none":
        updated_tools = []
    elif action == "set":
        if len(args) < 3:
            print("Usage: /agent tools <agent_name> set <tool_name ...>")
            return None
        requested_tools = sorted(set(args[2:]))
        unknown_tools = sorted(tool_name for tool_name in requested_tools if tool_name not in available_tools)
        if unknown_tools:
            print(
                f"Error: unknown tool(s) for agent '{profile.agent}': {', '.join(unknown_tools)}"
            )
            return None
        updated_tools = requested_tools
    else:
        print("Usage: /agent tools <agent_name> <all|none|set> [tool_name ...]")
        return None

    try:
        updater = engine.update_agent if hasattr(engine, "update_agent") else engine.update_agent_profile
        updater(
            profile.name,
            llm_profile=profile.llm_profile,
            tools=updated_tools,
            extra_prompts=list(profile.extra_prompts),
            tool_confirmation_default=_get_profile_confirmation_default(profile),
            tool_confirmation_overrides=_get_profile_confirmation_overrides(profile),
        )
        if updated_tools is None:
            print(f"Agent '{profile.name}' now allows all tools for flow '{profile.agent}'.")
        else:
            print(
                f"Agent '{profile.name}' allowed tools updated: "
                f"{', '.join(updated_tools) if updated_tools else '(none)'}"
            )
    except Exception as exc:
        print(f"Error: {exc}")
    return None


def _handle_agent_edit_command(
    args: list[str],
    engine: PocketCodeEngine,
) -> Optional[str]:
    if len(args) < 3:
        print("Usage: /agent edit <llm|prompts> <agent_name> <value...>")
        return None

    target = args[0].lower()
    profile_name = args[1]
    profile = _get_editable_agent_profile(engine, profile_name)
    if profile is None:
        return None

    try:
        updater = engine.update_agent if hasattr(engine, "update_agent") else engine.update_agent_profile
        if target == "llm":
            llm_profile = None if args[2].lower() in {"inherit", "none", "reset", "auto"} else args[2]
            updater(
                profile.name,
                llm_profile=llm_profile,
                tools=list(profile.tools) if profile.tools is not None else None,
                extra_prompts=list(profile.extra_prompts),
                tool_confirmation_default=_get_profile_confirmation_default(profile),
                tool_confirmation_overrides=_get_profile_confirmation_overrides(profile),
            )
            print(f"Agent '{profile.name}' LLM updated: {llm_profile or 'inherit'}")
            return None

        if target == "prompts":
            raw_prompt_args = args[2:]
            if len(raw_prompt_args) == 1 and raw_prompt_args[0].lower() in {"none", "clear", "reset"}:
                prompt_paths: list[str] = []
            else:
                prompt_paths = [prompt for prompt in raw_prompt_args if prompt.strip()]
            updater(
                profile.name,
                llm_profile=profile.llm_profile,
                tools=list(profile.tools) if profile.tools is not None else None,
                extra_prompts=prompt_paths,
                tool_confirmation_default=_get_profile_confirmation_default(profile),
                tool_confirmation_overrides=_get_profile_confirmation_overrides(profile),
            )
            print(
                f"Agent '{profile.name}' prompt paths updated: "
                f"{', '.join(prompt_paths) if prompt_paths else '(none)'}"
            )
            return None
    except Exception as exc:
        print(f"Error: {exc}")
        return None

    print("Usage: /agent edit <llm|prompts> <agent_name> <value...>")
    return None


def _handle_agent_policy_command(
    args: list[str],
    engine: PocketCodeEngine,
) -> Optional[str]:
    if len(args) < 3:
        print(
            "Usage: /agent policy <default|tool> <agent_name> "
            "<policy|tool_name policy>"
        )
        return None

    target = args[0].lower()
    profile_name = args[1]
    profile = _get_editable_agent_profile(engine, profile_name)
    if profile is None:
        return None

    current_default = _get_profile_confirmation_default(profile)
    current_overrides = _get_profile_confirmation_overrides(profile)

    try:
        if target == "default":
            if len(args) != 3:
                print("Usage: /agent policy default <agent_name> <allow|confirm|deny|reset>")
                return None
            policy = _parse_policy_or_reset(args[2])
            updater = engine.update_agent if hasattr(engine, "update_agent") else engine.update_agent_profile
            updater(
                profile.name,
                llm_profile=profile.llm_profile,
                tools=list(profile.tools) if profile.tools is not None else None,
                extra_prompts=list(profile.extra_prompts),
                tool_confirmation_default=policy,
                tool_confirmation_overrides=current_overrides,
            )
            print(
                f"Agent '{profile.name}' default tool policy set to: "
                f"{policy or 'inherit'}"
            )
            return None

        if target == "tool":
            if len(args) != 4:
                print(
                    "Usage: /agent policy tool <agent_name> "
                    "<tool_name> <allow|confirm|deny|reset>"
                )
                return None
            tool_name = args[2]
            policy = _parse_policy_or_reset(args[3])
            available_tools = set(engine.list_tools_for_agent(profile.agent))
            if tool_name not in available_tools:
                print(f"Error: unknown tool '{tool_name}' for agent '{profile.agent}'.")
                return None
            if policy is None:
                current_overrides.pop(tool_name, None)
            else:
                current_overrides[tool_name] = policy
            updater = engine.update_agent if hasattr(engine, "update_agent") else engine.update_agent_profile
            updater(
                profile.name,
                llm_profile=profile.llm_profile,
                tools=list(profile.tools) if profile.tools is not None else None,
                extra_prompts=list(profile.extra_prompts),
                tool_confirmation_default=current_default,
                tool_confirmation_overrides=current_overrides,
            )
            print(
                f"Agent '{profile.name}' tool policy updated: "
                f"{tool_name} -> {policy or 'inherit'}"
            )
            return None
    except Exception as exc:
        print(f"Error: {exc}")
        return None

    print(
        "Usage: /agent policy <default|tool> <agent_name> "
        "<policy|tool_name policy>"
    )
    return None


def _get_editable_agent_profile(
    engine: PocketCodeEngine,
    profile_name: str,
) -> Any:
    profile = engine.get_agent(profile_name) if hasattr(engine, "get_agent") else engine.get_agent_profile(profile_name)
    if profile is None:
        print(f"Error: agent not found: {profile_name}")
        return None
    if profile.source != "workspace" or profile.source_path is None:
        print(
            f"Error: agent '{profile_name}' is not workspace-backed. Clone it before editing."
        )
        return None
    return profile


def _get_profile_confirmation_default(profile: Any) -> str | None:
    tool_confirmation = profile.tool_confirmation if isinstance(profile.tool_confirmation, dict) else {}
    default_policy = tool_confirmation.get("default")
    return str(default_policy) if default_policy else None


def _get_profile_confirmation_overrides(profile: Any) -> dict[str, str]:
    tool_confirmation = profile.tool_confirmation if isinstance(profile.tool_confirmation, dict) else {}
    overrides = tool_confirmation.get("overrides", {})
    if not isinstance(overrides, dict):
        return {}
    return {
        str(tool_name): str(policy)
        for tool_name, policy in overrides.items()
        if tool_name and policy
    }


def print_agent_help() -> None:
    text = """
/agent Commands:
  /agent list                                 List all named agents (excludes synthesised flow defaults).
  /agent show [agent_name]                    Show details of an agent (default: active).
  /agent switch <agent_name>                  Activate an agent.
  /agent clone <source> <new_name>            Clone an agent to a new workspace agent.
    /agent edit llm <agent> <profile|inherit>   Set or clear the agent LLM override.
    /agent edit prompts <agent> <paths...>      Replace extra prompt paths.
    /agent edit prompts <agent> clear           Clear extra prompt paths.
  /agent tools <agent> all                    Allow all tools for a workspace agent.
  /agent tools <agent> none                   Deny all tools for a workspace agent.
  /agent tools <agent> set <tools...>
                                              Set the allowed tool list for a workspace agent.
  /agent policy default <agent> <allow|confirm|deny|reset>
                                              Set the agent default confirmation policy.
  /agent policy tool <agent> <tool> <allow|confirm|deny|reset>
                                              Set or clear a per-tool confirmation policy.
  /agent help                                 Show this help message.

Usage with /flow:
  /flow <flow_name> [--agent <agent_name>]

Compatibility:
    Agent shortcuts only: /ag and /ap map to /agent.
"""
    print(text)


def print_mode_help() -> None:
    text = """
/mode Commands:
  /mode list                                 List all available modes.
  /mode show [mode_name]                     Show details of a mode (default: active).
  /mode switch <mode_name>                   Activate a mode.
  /mode clear                                Clear the active mode.
  /mode help                                 Show this help message.
"""
    print(text)


def print_skill_help() -> None:
    text = """
/skill Commands:
  /skill list                                List all available skills grouped by top-level name prefix.
  /skill show <skill_name>                   Show details of a skill.
  /skill enable <skill_name>                 Enable a skill for the current session.
  /skill disable <skill_name>                Disable a skill for the current session.
  /skill help                                Show this help message.
"""
    print(text)


_parse_agent_profile_flag = _parse_agent_selection_flag
_handle_agent_profile_command = _handle_agent_command
print_agent_profile_help = print_agent_help
