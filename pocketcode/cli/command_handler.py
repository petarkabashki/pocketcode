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
    "/agents",
    "/agent",
    "/llms",
    "/llm",
    "/llm-agent",
    "/llm-handoff",
    "/tools",
    "/reload",
    "/status",
    "/context",
    "/confirm",
    "/agent-profile",
    "/agent-profile list",
    "/agent-profile show",
    "/agent-profile switch",
    "/agent-profile clone",
    "/copy",
    "/copy-all",
    "/exit",
    "/quit",
    "/ls",
    "/ag",
    "/ap",
    "/lm",
    "/la",
    "/lh",
    "/st",
    "/r",
    "/q",
]


def list_command_suggestions(engine: PocketCodeEngine) -> list[str]:
    return sorted(
        set(
            BASE_COMMAND_SUGGESTIONS
            + engine.list_agents()
            + engine.list_llm_profiles()
            + engine.list_agent_profiles()
        )
    )


def handle_command(
    command_input: str,
    engine: PocketCodeEngine,
    cli_context: Dict[str, Any],
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

    if command in {"/status"}:
        status = engine.status()
        print("Runtime status:")
        print(f"  Agent: {status['agent']}")
        print(f"  Global LLM Override: {status['global_llm_override']}")
        print(f"  Agent LLM Overrides: {status['agent_llm_overrides']}")
        print(f"  Handoff LLM Overrides: {status.get('handoff_llm_overrides', {})}")
        print(f"  Config LLM Overrides: {status.get('config_llm_overrides', {})}")
        print(f"  Default LLM Profile: {status['default_llm_profile']}")
        print(f"  Tool Confirmation (config): {status.get('tool_confirmation', {})}")
        print(f"  Tool Confirmation (session overrides): {status.get('session_tool_confirmation_overrides', {})}")
        return None

    if command in {"/agents", "/llms", "/tools", "/list"}:
        return _handle_list_command(command=command, args=args, engine=engine)

    if command in {
        "/agent",
        "/llm",
        "/llm-agent",
        "/llm-handoff",
        "/set",
    }:
        return _handle_set_command(command=command, args=args, engine=engine)

    if command == "/context":
        return _handle_context_command(args, cli_context)

    if command == "/confirm":
        return _handle_confirm_command(args, engine)

    if command == "/agent-profile":
        return _handle_agent_profile_command(args, engine)

    print(f"Unknown command: {command}")
    print_help()
    return None


def _normalize_command(command: str) -> str:
    aliases = {
        "/q": "/quit",
        "/r": "/reload",
        "/st": "/status",
        "/ls": "/list",
        "/ag": "/agent",
        "/ap": "/agent-profile",
        "/lm": "/llm",
        "/la": "/llm-agent",
        "/lh": "/llm-handoff",
    }
    return aliases.get(command, command)


def _handle_list_command(command: str, args: list[str], engine: PocketCodeEngine) -> Optional[str]:
    if command == "/agents":
        scope = "agents"
    elif command == "/llms":
        scope = "llms"
    elif command == "/tools":
        scope = "tools"
    else:
        if not args:
            print("Usage: /list <agents|llms|tools> [agent]")
            return None
        scope = args[0].lower()
        args = args[1:]

    if scope == "agents":
        agents = engine.list_agents()
        print("Available agents:")
        for agent in agents:
            marker = "*" if agent == engine.get_current_agent() else " "
            print(f"  {marker} {agent}")
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
        target_agent = args[0] if args else engine.get_current_agent()
        if not target_agent:
            print("No active agent selected. Use /agent <name> or /tools <agent_name>.")
            return None
        try:
            tool_descriptions = engine.describe_tools_for_agent(target_agent)
        except Exception as exc:
            print(f"Error: {exc}")
            return None

        print(f"Tools for agent '{target_agent}':")
        for tool in tool_descriptions:
            print(f"  - {tool['name']}: {tool.get('description', '')}")
        return None

    print(f"Unknown list scope: {scope}")
    print("Usage: /list <agents|llms|tools> [agent]")
    return None


def _handle_set_command(command: str, args: list[str], engine: PocketCodeEngine) -> Optional[str]:
    if command == "/set":
        if not args:
            print(
                "Usage: /set <agent|llm|llm-agent|llm-handoff> <args...>"
            )
            return None
        command = f"/{args[0].lower()}"
        args = args[1:]

    if command == "/agent":
        if not args:
            current_agent = engine.get_current_agent()
            current_profile = engine.active_agent_profile
            print(f"Current agent: {current_agent or 'auto'}")
            if current_profile:
                print(f"Current agent profile: {current_profile.name}")
            print("Usage: /agent <agent_name|auto> [--agent-profile <profile_name>]")
            return None
        target, profile_name = _parse_agent_profile_flag(args)
        try:
            if target.lower() == "auto":
                engine.set_agent(None)
                print("Agent selection reset to runtime default/handoff.")
            else:
                engine.set_agent(target)
                print(f"Selected agent: {target}")
            if profile_name is not None:
                try:
                    engine.set_active_agent_profile(profile_name)
                    print(f"Agent profile activated: {profile_name}")
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

    if command == "/llm-agent":
        if len(args) < 2:
            print("Usage: /llm-agent <agent_name> <profile_name|none>")
            return None
        agent_name, profile_name = args[0], args[1]
        try:
            if profile_name.lower() in {"none", "reset", "auto"}:
                engine.set_agent_llm_override(agent_name, None)
                print(f"Agent-specific LLM override cleared for: {agent_name}")
            else:
                engine.set_agent_llm_override(agent_name, profile_name)
                print(f"Agent-specific LLM override set: {agent_name} -> {profile_name}")
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
    print("Usage: /set <agent|llm|llm-agent|llm-handoff> <args...>")
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


def print_help() -> None:
    help_text = """
Pocketcode Commands:
  /help                          Show this help message.
  /list <scope> [opts]           List entities by scope.
                                 Scopes: agents|llms|tools [agent for tools]
  /set <target> <args...>        Set runtime selection/override.
                                 Targets: agent|llm|llm-agent|llm-handoff
  /reload                        Reload plugins and runtime catalogs.
  /status                        Show runtime status.
  /context <cmd> [opts]          Manage context. Run '/context help'.
  /confirm <cmd> [opts]          Manage tool confirmation policies. Run '/confirm help'.
  /agent-profile <cmd> [opts]    Manage agent profiles. Run '/agent-profile help'.
  /copy, /copy-all               Copy response text (Textual UI).
  /exit, /quit                   Exit Pocketcode.

Compatibility aliases:
  /agents    -> /list agents
  /llms      -> /list llms
  /tools     -> /list tools
  /agent     -> /set agent
  /ap        -> /agent-profile
  /llm       -> /set llm
  /llm-agent -> /set llm-agent
  /llm-handoff -> /set llm-handoff

Keyboard shortcuts (Textual UI):
  Tab                           Complete current prompt input.
  F1 / F2 / F3 / F4 / F5        Switch Chat / Control / Profiles / Context / Run views.
  F6                            Select next agent.
  F7 or Ctrl+P                  Select next profile for the current agent.
  F8                            Select next global LLM override.
  F9                            Toggle the left navigation panel.
  F10                           Toggle the right inspector panel.
  F11                           Toggle the second header row.
  Ctrl+W                        Cycle workspace mode presets.
  Alt+1 / Alt+2 / Alt+3         Switch Chat / Control / Profiles views.
  Alt+4 / Alt+5                 Switch Context / Run views.
  Ctrl+Shift+A                  Copy full response console output.
  Ctrl+Y                        Copy last assistant response.
  Ctrl+Q                        Quit Textual UI.

Textual convenience commands:
  /copy                         Copy last assistant response.
  /copy-all                     Copy full response console output.

Shortcut aliases:
  /ls   /list
  /ag   /agent
  /lm   /llm
  /la   /llm-agent
  /lh   /llm-handoff
  /st   /status
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


def _parse_agent_profile_flag(args: list[str]) -> tuple[str, str | None]:
    """Extract ``--agent-profile <name>`` from *args*.

    Returns a tuple of ``(positional_target, profile_name)`` where
    *positional_target* is the first non-flag argument and *profile_name* is
    the value following ``--agent-profile`` (or ``None`` if not supplied).
    """
    profile_name: str | None = None
    cleaned: list[str] = []
    i = 0
    while i < len(args):
        if args[i] in {"--agent-profile", "--profile"} and i + 1 < len(args):
            profile_name = args[i + 1]
            i += 2
        else:
            cleaned.append(args[i])
            i += 1
    return (cleaned[0] if cleaned else ""), profile_name


def _handle_agent_profile_command(
    args: list[str],
    engine: PocketCodeEngine,
) -> Optional[str]:
    """Dispatch /agent-profile sub-commands: list | show | switch | clone."""
    if not args:
        print_agent_profile_help()
        return None

    subcommand = args[0].lower()
    sub_args = args[1:]

    if subcommand == "help":
        print_agent_profile_help()
        return None

    if subcommand == "list":
        profiles = engine.list_agent_profiles()
        if not profiles:
            print("No agent profiles available.")
            return None
        active = engine.active_agent_profile
        print("Available agent profiles:")
        for name in profiles:
            marker = "*" if (active and active.name == name) else " "
            print(f"  {marker} {name}")
        return None

    if subcommand == "show":
        if sub_args:
            profile = engine.get_agent_profile(sub_args[0])
            if profile is None:
                print(f"Agent profile not found: {sub_args[0]}")
                return None
        else:
            profile = engine.get_agent_profile()
            if not profile:
                print("No agent profile is currently active.")
                return None
        print(f"Agent Profile: {profile.name}")
        print(f"  Agent    : {profile.agent}")
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
            print("Usage: /agent-profile switch <profile_name>")
            return None
        name = sub_args[0]
        try:
            engine.set_active_agent_profile(name)
            print(f"Agent profile activated: {name}")
        except ValueError as exc:
            print(f"Error: {exc}")
        return None

    if subcommand == "clone":
        if len(sub_args) < 2:
            print("Usage: /agent-profile clone <source_profile> <new_profile_name>")
            return None
        src, new_name = sub_args[0], sub_args[1]
        try:
            engine.clone_agent_profile(src, new_name)
            print(f"Cloned profile '{src}' \u2192 '{new_name}'.")
        except (KeyError, ValueError) as exc:
            print(f"Error: {exc}")
        return None

    print(f"Unknown /agent-profile subcommand: {subcommand}")
    print_agent_profile_help()
    return None


def print_agent_profile_help() -> None:
    text = """
/agent-profile Commands:
  /agent-profile list                         List all available agent profiles.
  /agent-profile show [profile_name]          Show details of a profile (default: active).
  /agent-profile switch <profile_name>        Activate an agent profile.
  /agent-profile clone <source> <new_name>    Clone a profile to a new workspace profile.
  /agent-profile help                         Show this help message.

Usage with /agent:
  /agent <agent_name> [--agent-profile <profile_name>]
"""
    print(text)
