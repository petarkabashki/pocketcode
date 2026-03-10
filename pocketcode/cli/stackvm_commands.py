from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


def handle_stackvm_command(args: list[str], engine: Any) -> Optional[str]:
    if not args:
        print_stackvm_help()
        return None

    subcommand = args[0].lower()
    sub_args = args[1:]

    if subcommand == "help":
        print_stackvm_help()
        return None

    if subcommand == "list":
        scope = sub_args[0].lower() if sub_args else "all"
        if scope in {"all", "flows"}:
            print("StackVM flows:")
            flow_names = []
            for flow_name in engine.list_flows():
                try:
                    details = engine.describe_flow(flow_name)
                except Exception:
                    continue
                if str(details.get("execution_mode") or "").strip().lower() == "vm":
                    flow_names.append(flow_name)
            if flow_names:
                for flow_name in flow_names:
                    print(f"  {flow_name}")
            else:
                print("  (none)")
        if scope in {"all", "scripts"}:
            print("StackVM scripts:")
            scripts = engine.list_stackvm_scripts()
            if scripts:
                for script_name in scripts:
                    print(f"  {script_name}")
            else:
                print("  (none)")
        return None

    if subcommand == "create":
        return _handle_stackvm_create(sub_args, engine)

    if subcommand in {"inspect", "show"}:
        return _handle_stackvm_inspect(sub_args, engine)

    if subcommand in {"alter", "edit"}:
        return _handle_stackvm_alter(sub_args, engine)

    if subcommand == "run":
        return _handle_stackvm_run(sub_args, engine, debug=False)

    if subcommand == "debug":
        return _handle_stackvm_run(sub_args, engine, debug=True)

    print(f"Unknown /stackvm subcommand: {subcommand}")
    print_stackvm_help()
    return None


def _handle_stackvm_create(args: list[str], engine: Any) -> Optional[str]:
    if not args:
        print("Usage: /stackvm create <flow|script|agent> ...")
        return None

    kind = args[0].lower()
    rest = args[1:]

    if kind == "flow":
        if not rest:
            print("Usage: /stackvm create flow <name> [--entry <word>] [--agent <agent_name>]")
            return None
        name = rest[0]
        options = _parse_flag_pairs(rest[1:], valued_flags={"--entry", "--agent"})
        created = engine.create_stackvm_flow(
            name,
            entry=str(options.get("--entry") or "decide"),
            agent_name=str(options["--agent"]) if options.get("--agent") else None,
        )
        print(f"Created StackVM flow '{created['name']}' at {created['path']}.")
        print(f"  Entry: {created['entry']}")
        if created.get("agent"):
            agent = created["agent"]
            print(f"  Agent: {agent['name']} -> {agent['flow']} ({agent['path']})")
        return None

    if kind == "script":
        if not rest:
            print("Usage: /stackvm create script <name> [--entry <word>]")
            return None
        name = rest[0]
        options = _parse_flag_pairs(rest[1:], valued_flags={"--entry"})
        created = engine.create_stackvm_script(name, entry=str(options.get("--entry") or "main"))
        print(f"Created StackVM script '{created['name']}' at {created['path']}.")
        print(f"  Entry: {created['entry']}")
        return None

    if kind == "agent":
        if len(rest) != 2:
            print("Usage: /stackvm create agent <agent_name> <flow_name>")
            return None
        created = engine.create_stackvm_agent(rest[0], flow_name=rest[1])
        print(f"Created StackVM agent '{created['name']}' at {created['path']}.")
        print(f"  Flow: {created['flow']}")
        return None

    print("Usage: /stackvm create <flow|script|agent> ...")
    return None


def _handle_stackvm_inspect(args: list[str], engine: Any) -> Optional[str]:
    if len(args) < 2:
        print("Usage: /stackvm inspect <flow|script|agent> <name_or_path> [--entry <word>]")
        return None

    kind = args[0].lower()
    target = args[1]
    options = _parse_flag_pairs(args[2:], valued_flags={"--entry"})
    details = engine.inspect_stackvm_target(kind, target, entry=options.get("--entry"))

    print(f"StackVM {details['target_kind']}: {details['name']}")
    if details.get("path"):
        print(f"  Path          : {details['path']}")
    if details.get("flow"):
        print(f"  Flow          : {details['flow']}")
    if details.get("agent"):
        print(f"  Agent         : {details['agent']}")
    print(f"  Execution     : {details.get('execution_mode') or 'vm'}")
    print(f"  Entry         : {details.get('vm_entry') or '(none)'}")
    print(f"  Source files  : {details.get('source_files') or []}")
    print(f"  Tokens        : {details.get('token_count', 0)}")
    print(f"  Warnings      : {details.get('warning_count', 0)}")
    if details.get("warning_count"):
        for warning in details.get("warnings", []):
            code = warning.get("code") or "warning"
            location = warning.get("location")
            message = warning.get("message") or ""
            prefix = f"{code} ({location})" if location else str(code)
            print(f"    - {prefix}: {message}")
    print("")
    print("Expanded StackVM:")
    print((details.get("expanded_source") or details.get("source") or "").rstrip())
    return None


def _handle_stackvm_alter(args: list[str], engine: Any) -> Optional[str]:
    if len(args) < 3:
        print("Usage: /stackvm alter <flow|script|agent> <name_or_path> <source_file>")
        return None

    kind = args[0].lower()
    target = args[1]
    source_file = _resolve_input_file(args[2])
    if not source_file.is_file():
        print(f"Error: source file not found: {source_file}")
        return None
    text = source_file.read_text(encoding="utf-8")

    if kind in {"flow", "agent"}:
        updated = engine.update_markdown_asset(kind, target, markdown_text=text)
        print(f"Updated StackVM {kind} '{updated['name']}' from {source_file} into {updated['path']}.")
        return None

    if kind == "script":
        updated = engine.update_stackvm_script(target, source_text=text)
        print(f"Updated StackVM script '{updated['name']}' from {source_file} into {updated['path']}.")
        if updated.get("warnings"):
            print(f"  Warnings: {len(updated['warnings'])}")
        return None

    print("Usage: /stackvm alter <flow|script|agent> <name_or_path> <source_file>")
    return None


def _handle_stackvm_run(args: list[str], engine: Any, *, debug: bool) -> Optional[str]:
    if len(args) < 2:
        usage = "/stackvm debug <flow|script|agent> <name_or_path> [--input <text>] [--entry <word>]"
        if not debug:
            usage = "/stackvm run <flow|script|agent> <name_or_path> [--input <text>] [--entry <word>] [--debug]"
        print(f"Usage: {usage}")
        return None

    kind = args[0].lower()
    target = args[1]
    options = _parse_flag_pairs(args[2:], valued_flags={"--input", "--entry"})
    if "--debug" in args[2:]:
        debug = True

    result = engine.run_stackvm_target(
        kind,
        target,
        request=str(options.get("--input") or ""),
        entry=options.get("--entry"),
        debug=debug,
        auto_confirm_tools=True,
    )

    print(f"StackVM run complete for {kind} '{target}'.")
    if result.get("error_message"):
        print(f"  Error   : {result['error_message']}")
    print(f"  Output  : {result.get('output') or ''}")
    print(f"  Warnings: {result.get('run_summary', {}).get('vm_validation_warning_count', 0)}")
    if result.get("tool_history"):
        print(f"  Tools   : {len(result['tool_history'])} call(s)")
    if debug:
        print(f"  Trace   : {result.get('trace_count', 0)} step(s)")
        if result.get("trace"):
            print("")
            print("Trace:")
            for index, item in enumerate(result["trace"], start=1):
                word = item.get("word")
                op = item.get("op")
                detail = word if word else item.get("value")
                print(f"  {index:02d}. {op}: {detail} -> stack={item.get('stack')}")
        print("")
        print("Expanded StackVM:")
        print(str(result.get("last_vm_expanded_source") or result.get("last_vm_source") or "").rstrip())
    return None


def print_stackvm_help() -> None:
    text = """
/stackvm Commands:
  /stackvm list [flows|scripts]                          List registered StackVM flows and workspace scripts.
  /stackvm create flow <name> [--entry <word>] [--agent <agent_name>]
                                                         Create a StackVM-backed Markdown flow scaffold.
  /stackvm create script <name> [--entry <word>]         Create a standalone StackVM script under vm/.
  /stackvm create agent <agent_name> <flow_name>         Create a workspace agent bound to a StackVM flow.
  /stackvm inspect <flow|script|agent> <target> [--entry <word>]
                                                         Show compiled StackVM metadata, warnings, and expanded source.
  /stackvm run <flow|script|agent> <target> [--input <text>] [--entry <word>] [--debug]
                                                         Execute a StackVM target once from the CLI.
  /stackvm debug <flow|script|agent> <target> [--input <text>] [--entry <word>]
                                                         Execute and print the StackVM trace.
  /stackvm alter <flow|script|agent> <target> <source_file>
                                                         Replace a StackVM flow, script, or agent from a local file.
  /stackvm help                                          Show this help message.
"""
    print(text)


def _resolve_input_file(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def _parse_flag_pairs(args: list[str], *, valued_flags: set[str]) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    index = 0
    while index < len(args):
        item = args[index]
        if item in valued_flags:
            if index + 1 >= len(args):
                raise ValueError(f"Missing value for flag {item}")
            parsed[item] = args[index + 1]
            index += 2
            continue
        if item.startswith("--"):
            parsed[item] = "true"
        index += 1
    return parsed
