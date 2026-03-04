from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from pocketcode.core.engine import PocketCodeEngine

logger = logging.getLogger(__name__)


def handle_command(
    command_input: str,
    engine: PocketCodeEngine,
    cli_context: Dict[str, Any],
) -> Optional[str]:
    parts = command_input.strip().split()
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
        print("Reloaded plugins, workflows, tools, and LLM profile mappings.")
        return None

    if command in {"/status"}:
        status = engine.status()
        print("Runtime status:")
        print(f"  Workflow: {status['workflow']}")
        print(f"  Agent: {status['agent']}")
        print(f"  Global LLM Override: {status['global_llm_override']}")
        print(f"  Agent LLM Overrides: {status['agent_llm_overrides']}")
        print(f"  Node LLM Overrides: {status.get('node_llm_overrides', {})}")
        print(f"  Handoff LLM Overrides: {status.get('handoff_llm_overrides', {})}")
        print(f"  Config LLM Overrides: {status.get('config_llm_overrides', {})}")
        print(f"  Default LLM Profile: {status['default_llm_profile']}")
        print(f"  Tool Confirmation (config): {status.get('tool_confirmation', {})}")
        print(f"  Tool Confirmation (session overrides): {status.get('session_tool_confirmation_overrides', {})}")
        print(f"  Components: {len(status.get('available_components', []))}")
        return None

    if command in {"/components", "/workflows", "/modes", "/agents", "/llms", "/tools", "/list"}:
        return _handle_list_command(command=command, args=args, engine=engine)

    if command in {
        "/workflow",
        "/mode",
        "/agent",
        "/llm",
        "/llm-agent",
        "/llm-node",
        "/llm-handoff",
        "/set",
    }:
        return _handle_set_command(command=command, args=args, engine=engine)

    if command == "/context":
        return _handle_context_command(args, cli_context)

    if command == "/confirm":
        return _handle_confirm_command(args, engine)

    print(f"Unknown command: {command}")
    print_help()
    return None


def _normalize_command(command: str) -> str:
    aliases = {
        "/q": "/quit",
        "/r": "/reload",
        "/st": "/status",
        "/ls": "/list",
        "/wf": "/workflow",
        "/ag": "/agent",
        "/lm": "/llm",
        "/la": "/llm-agent",
        "/ln": "/llm-node",
        "/lh": "/llm-handoff",
    }
    return aliases.get(command, command)


def _handle_list_command(command: str, args: list[str], engine: PocketCodeEngine) -> Optional[str]:
    if command == "/components":
        scope = "components"
    elif command in {"/workflows", "/modes"}:
        scope = "workflows"
    elif command == "/agents":
        scope = "agents"
    elif command == "/llms":
        scope = "llms"
    elif command == "/tools":
        scope = "tools"
    else:
        if not args:
            print("Usage: /list <workflows|agents|llms|components|tools> [agent]")
            return None
        scope = args[0].lower()
        args = args[1:]

    if scope in {"workflows", "modes"}:
        workflows = engine.list_workflows()
        print("Available workflows:")
        for workflow in workflows:
            marker = "*" if workflow == engine.get_current_workflow() else " "
            print(f"  {marker} {workflow}")
        return None

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

    if scope == "components":
        components = engine.describe_components()
        print("Available components:")
        for item in components:
            print(f"  - {item['name']} ({item['kind']}, plugin={item['plugin']}, source={item['source']})")
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
    print("Usage: /list <workflows|agents|llms|components|tools> [agent]")
    return None


def _handle_set_command(command: str, args: list[str], engine: PocketCodeEngine) -> Optional[str]:
    if command == "/set":
        if not args:
            print(
                "Usage: /set <workflow|agent|llm|llm-agent|llm-node|llm-handoff> <args...>"
            )
            return None
        command = f"/{args[0].lower()}"
        args = args[1:]

    if command in {"/workflow", "/mode"}:
        if not args:
            print("Usage: /workflow <workflow_name>")
            return None
        try:
            engine.set_workflow(args[0])
            print(f"Selected workflow: {args[0]}")
        except Exception as exc:
            print(f"Error: {exc}")
        return None

    if command == "/agent":
        if not args:
            print(f"Current agent: {engine.get_current_agent() or 'auto'}")
            print("Usage: /agent <agent_name|auto>")
            return None
        target = args[0]
        try:
            if target.lower() == "auto":
                engine.set_agent(None)
                print("Agent selection reset to workflow default/hand-off.")
            else:
                engine.set_agent(target)
                print(f"Selected agent: {target}")
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

    if command == "/llm-node":
        if len(args) < 2:
            print("Usage: /llm-node <workflow.node|node> <profile_name|none>")
            return None
        node_ref, profile_name = args[0], args[1]
        try:
            if profile_name.lower() in {"none", "reset", "auto"}:
                engine.set_node_llm_override(node_ref=node_ref, profile_name=None)
                print(f"Node-specific LLM override cleared for: {node_ref}")
            else:
                engine.set_node_llm_override(node_ref=node_ref, profile_name=profile_name)
                print(f"Node-specific LLM override set: {node_ref} -> {profile_name}")
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
    print("Usage: /set <workflow|agent|llm|llm-agent|llm-node|llm-handoff> <args...>")
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
                                 Scopes: workflows|agents|llms|components|tools [agent]
  /set <target> <args...>        Set runtime selection/override.
                                 Targets: workflow|agent|llm|llm-agent|llm-node|llm-handoff
  /reload                        Reload plugins, workflows, and runtime catalogs.
  /status                        Show runtime status.
  /context <cmd> [opts]          Manage context. Run '/context help'.
  /confirm <cmd> [opts]          Manage tool confirmation policies. Run '/confirm help'.
  /copy, /copy-all               Copy response text (Textual UI).
  /exit, /quit                   Exit Pocketcode.

Compatibility aliases:
  /workflows -> /list workflows
  /agents    -> /list agents
  /llms      -> /list llms
  /components-> /list components
  /tools     -> /list tools
  /workflow  -> /set workflow
  /mode      -> /set workflow
  /agent     -> /set agent
  /llm       -> /set llm
  /llm-agent -> /set llm-agent
  /llm-node  -> /set llm-node
  /llm-handoff -> /set llm-handoff

Keyboard shortcuts (Textual UI):
  Tab                           Complete current prompt input.
  Ctrl+]                        Select next agent.
  Ctrl+[                        Select next global LLM override.
  Ctrl+T                        Toggle top stats panel.
  Ctrl+Space                    Complete current prompt input.
  Ctrl+Shift+A                  Copy full response console output.
  Ctrl+Y                        Copy last assistant response.
  Ctrl+Q                        Quit Textual UI.

Textual convenience commands:
  /copy                         Copy last assistant response.
  /copy-all                     Copy full response console output.

Shortcut aliases:
  /ls   /list
  /wf   /workflow
  /ag   /agent
  /lm   /llm
  /la   /llm-agent
  /ln   /llm-node
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
