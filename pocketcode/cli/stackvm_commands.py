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
        if scope in {"all", "stdlib"}:
            _print_stackvm_stdlib_list(engine)
        return None

    if subcommand == "stdlib":
        return _handle_stackvm_stdlib(sub_args, engine)

    if subcommand == "create":
        return _handle_stackvm_create(sub_args, engine)

    if subcommand in {"inspect", "show"}:
        return _handle_stackvm_inspect(sub_args, engine)

    if subcommand == "check":
        return _handle_stackvm_check(sub_args, engine)

    if subcommand == "explain":
        return _handle_stackvm_explain(sub_args, engine)

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
        _print_stackvm_update_warnings(created.get("warnings"))
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
    analysis = details.get("analysis", {})
    if not isinstance(analysis, dict):
        analysis = {}

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
    print(f"  Diagnostics   : {details.get('diagnostic_count', 0)}")
    print(f"  Effects       : {', '.join(details.get('effect_kinds') or []) or '(none)'}")
    print(f"  Host surfaces : {', '.join(analysis.get('host_surfaces_used') or []) or 'core-only'}")
    print(f"  Standalone    : {'yes' if analysis.get('standalone_script_compatible') else 'no'}")
    print(f"  Stdlib req    : {', '.join(details.get('stdlib_modules_requested') or []) or '(none)'}")
    print(f"  Stdlib used   : {', '.join(details.get('stdlib_modules_resolved') or []) or '(none)'}")
    print(f"  Max stack     : {details.get('max_stack_depth', 0)}")
    print(f"  Final min     : {details.get('final_min_stack_depth', 0)}")
    print(f"  Final shape   : {analysis.get('final_stack_shape', []) if isinstance(analysis.get('final_stack_shape'), list) else []}")
    unresolved_stdlib = details.get("stdlib_unresolved_refs") or []
    if unresolved_stdlib:
        print(f"  Stdlib miss   : {', '.join(unresolved_stdlib)}")
    if details.get("warning_count"):
        for warning in details.get("warnings", []):
            code = warning.get("code") or "warning"
            location = warning.get("location")
            authored_location = warning.get("authored_location")
            message = warning.get("message") or ""
            prefix = f"{code} ({location})" if location else str(code)
            if authored_location:
                prefix += f" [authored: {authored_location}]"
            print(f"    - {prefix}: {message}")
    if details.get("diagnostic_count"):
        for diagnostic in details.get("diagnostics", []):
            code = diagnostic.get("code") or "diagnostic"
            location = diagnostic.get("location")
            authored_location = diagnostic.get("authored_location")
            message = diagnostic.get("message") or ""
            severity = diagnostic.get("severity") or "warning"
            prefix = f"{severity} {code}"
            if location:
                prefix = f"{prefix} ({location})"
            if authored_location:
                prefix = f"{prefix} [authored: {authored_location}]"
            print(f"    - {prefix}: {message}")
    print("")
    print("Expanded StackVM:")
    print((details.get("expanded_source") or details.get("source") or "").rstrip())
    return None


def _handle_stackvm_check(args: list[str], engine: Any) -> Optional[str]:
    if len(args) < 2:
        print("Usage: /stackvm check <flow|script|agent> <name_or_path> [--entry <word>]")
        return None

    kind = args[0].lower()
    target = args[1]
    options = _parse_flag_pairs(args[2:], valued_flags={"--entry"})
    details = engine.inspect_stackvm_target(kind, target, entry=options.get("--entry"))
    analysis = details.get("analysis", {})
    if not isinstance(analysis, dict):
        analysis = {}

    print(f"StackVM check for {details['target_kind']} '{details['name']}'")
    print(f"  Entry       : {details.get('vm_entry') or '(none)'}")
    print(f"  Warnings    : {details.get('warning_count', 0)}")
    print(f"  Diagnostics : {details.get('diagnostic_count', 0)}")
    print(f"  Effects     : {', '.join(details.get('effect_kinds') or []) or '(none)'}")
    print(f"  Host        : {', '.join(analysis.get('host_surfaces_used') or []) or 'core-only'}")
    print(f"  Standalone  : {'yes' if analysis.get('standalone_script_compatible') else 'no'}")
    print(f"  Stdlib req  : {', '.join(details.get('stdlib_modules_requested') or []) or '(none)'}")
    print(f"  Stdlib used : {', '.join(details.get('stdlib_modules_resolved') or []) or '(none)'}")
    print(f"  Max stack   : {details.get('max_stack_depth', 0)}")
    print(f"  Final min   : {details.get('final_min_stack_depth', 0)}")
    print(f"  Final shape : {analysis.get('final_stack_shape', []) if isinstance(analysis.get('final_stack_shape'), list) else []}")
    unresolved_stdlib = details.get("stdlib_unresolved_refs") or []
    if unresolved_stdlib:
        print(f"  Stdlib miss : {', '.join(unresolved_stdlib)}")

    if details.get("warning_count"):
        print("")
        print("Warnings:")
        for warning in details.get("warnings", []):
            code = warning.get("code") or "warning"
            location = warning.get("location")
            authored_location = warning.get("authored_location")
            message = warning.get("message") or ""
            prefix = f"{code} ({location})" if location else str(code)
            if authored_location:
                prefix += f" [authored: {authored_location}]"
            print(f"  - {prefix}: {message}")

    if details.get("diagnostic_count"):
        print("")
        print("Diagnostics:")
        for diagnostic in details.get("diagnostics", []):
            code = diagnostic.get("code") or "diagnostic"
            location = diagnostic.get("location")
            authored_location = diagnostic.get("authored_location")
            message = diagnostic.get("message") or ""
            severity = diagnostic.get("severity") or "warning"
            prefix = f"{severity} {code}"
            if location:
                prefix = f"{prefix} ({location})"
            if authored_location:
                prefix = f"{prefix} [authored: {authored_location}]"
            print(f"  - {prefix}: {message}")

    if not details.get("warning_count") and not details.get("diagnostic_count"):
        print("")
        print("Check passed with no warnings or diagnostics.")

    return None


def _handle_stackvm_explain(args: list[str], engine: Any) -> Optional[str]:
    if len(args) < 2:
        print("Usage: /stackvm explain <flow|script|agent> <name_or_path> [--entry <word>]")
        return None

    kind = args[0].lower()
    target = args[1]
    options = _parse_flag_pairs(args[2:], valued_flags={"--entry"})
    details = engine.inspect_stackvm_target(kind, target, entry=options.get("--entry"))
    analysis = details.get("analysis", {})
    if not isinstance(analysis, dict):
        analysis = {}
    expansion = details.get("expansion_metadata", {})
    if not isinstance(expansion, dict):
        expansion = {}

    print(f"StackVM explain for {details['target_kind']} '{details['name']}'")
    print(f"  Entry       : {details.get('vm_entry') or '(none)'}")
    print(f"  Tokens      : {details.get('token_count', 0)}")
    print(f"  Effects     : {', '.join(details.get('effect_kinds') or []) or '(none)'}")
    print(f"  Host        : {', '.join(analysis.get('host_surfaces_used') or []) or 'core-only'}")
    print(f"  Standalone  : {'yes' if analysis.get('standalone_script_compatible') else 'no'}")
    print(f"  Stdlib req  : {', '.join(details.get('stdlib_modules_requested') or []) or '(none)'}")
    print(f"  Stdlib used : {', '.join(details.get('stdlib_modules_resolved') or []) or '(none)'}")
    print(f"  Max stack   : {details.get('max_stack_depth', 0)}")
    print(f"  Final min   : {details.get('final_min_stack_depth', 0)}")
    print(f"  Final shape : {analysis.get('final_stack_shape', []) if isinstance(analysis.get('final_stack_shape'), list) else []}")
    print(f"  Warnings    : {details.get('warning_count', 0)}")
    print(f"  Diagnostics : {details.get('diagnostic_count', 0)}")
    print(f"  Macros      : {expansion.get('expansion_count', 0)} expansion(s)")
    unresolved_stdlib = details.get("stdlib_unresolved_refs") or []
    if unresolved_stdlib:
        print(f"  Stdlib miss : {', '.join(unresolved_stdlib)}")

    macro_names = expansion.get("macro_names", [])
    if isinstance(macro_names, list) and macro_names:
        print("")
        print("Macro Trace:")
        for index, name in enumerate(expansion.get("expansion_trace", []), start=1):
            print(f"  {index:02d}. {name}")

    frames = expansion.get("expansion_frames", [])
    if isinstance(frames, list) and frames:
        print("")
        print("Expansion Frames:")
        for index, frame in enumerate(frames, start=1):
            macro_name = frame.get("macro_name") or "macro"
            call_site = frame.get("call_site") or "unknown call site"
            generated_by = frame.get("generated_by")
            label = f"  {index:02d}. {macro_name} @ {call_site}"
            if generated_by:
                label += f" (generated by {generated_by})"
            print(label)

    analysis_decisions = analysis.get("analysis_decisions", [])
    if isinstance(analysis_decisions, list) and analysis_decisions:
        print("")
        print("Analysis Decisions:")
        for decision in analysis_decisions:
            if not isinstance(decision, dict):
                continue
            scope_name = str(decision.get("scope") or "main")
            reason = str(decision.get("reason") or "decision")
            detail = str(decision.get("detail") or "")
            severity = str(decision.get("severity") or "info")
            location = decision.get("location")
            authored_location = decision.get("authored_location")
            suffix = f" @ {location}" if location else ""
            if authored_location:
                suffix += f" [authored: {authored_location}]"
            print(f"  - {severity} {scope_name}: {reason}{suffix} - {detail}")

    scope_summaries = analysis.get("scope_summaries", [])
    if isinstance(scope_summaries, list) and scope_summaries:
        print("")
        print("Scope Summaries:")
        for summary in scope_summaries:
            if not isinstance(summary, dict):
                continue
            scope_name = str(summary.get("scope") or "main")
            summary_kind = str(summary.get("kind") or "region")
            if summary_kind == "merge":
                branch_shapes = summary.get("branch_output_shapes")
                if not isinstance(branch_shapes, list):
                    branch_shapes = []
                merged_shape = summary.get("merged_stack_shape")
                if not isinstance(merged_shape, list):
                    merged_shape = []
                reason = str(summary.get("reason") or "branch-merge")
                precision = str(summary.get("precision") or "merged")
                location = summary.get("location")
                authored_location = summary.get("authored_location")
                suffix = f" @ {location}" if location else ""
                if authored_location:
                    suffix += f" [authored: {authored_location}]"
                print(f"  - {scope_name}{suffix}: reason={reason}, precision={precision}, branches={branch_shapes} -> merged={merged_shape}")
                continue
            input_shape = summary.get("input_stack_shape")
            if not isinstance(input_shape, list):
                input_shape = []
            output_shape = summary.get("output_stack_shape")
            if not isinstance(output_shape, list):
                output_shape = []
            effects = summary.get("effect_kinds")
            if not isinstance(effects, list):
                effects = []
            diagnostics = int(summary.get("diagnostic_count", 0) or 0)
            unknown_output_count = int(summary.get("unknown_output_count", 0) or 0)
            shape_preserved = bool(summary.get("shape_preserved"))
            location = summary.get("location")
            authored_location = summary.get("authored_location")
            definition_location = summary.get("definition_location")
            suffix = f" @ {location}" if location else ""
            if authored_location:
                suffix += f" [authored: {authored_location}]"
            if definition_location:
                suffix += f" [defined: {definition_location}]"
            print(
                f"  - {scope_name}{suffix}: in={input_shape} -> out={output_shape}, "
                f"effects={', '.join(effects) or '(none)'}, diagnostics={diagnostics}, "
                f"unknowns={unknown_output_count}, shape_preserved={shape_preserved}"
            )

    shape_flow = analysis.get("shape_flow", [])
    if isinstance(shape_flow, list) and shape_flow:
        print("")
        print("Shape Flow:")
        for scope_name, steps in _group_shape_flow(shape_flow).items():
            print(f"  {scope_name}:")
            for index, step in enumerate(steps, start=1):
                depth = int(step.get("depth", 0) or 0)
                indent = "    " + ("  " * depth)
                label = step.get("label") or step.get("op") or "step"
                stack_shape = step.get("stack_shape", [])
                location = step.get("location")
                authored_location = step.get("authored_location")
                suffix = f" @ {location}" if location else ""
                if authored_location:
                    suffix += f" [authored: {authored_location}]"
                print(f"{indent}{index:02d}. {label} -> {stack_shape}{suffix}")

    word_summaries = analysis.get("word_metadata_summary", {})
    if isinstance(word_summaries, dict) and word_summaries:
        print("")
        print("User Word Contracts:")
        for word_name, summary in sorted(word_summaries.items()):
            if not isinstance(summary, dict):
                continue
            pops = summary.get("pops")
            pushes = summary.get("pushes")
            effect_kind = summary.get("effect_kind") or "unknown"
            host_surface = summary.get("host_surface") or "core"
            definition_location = summary.get("definition_location")
            output_shape = summary.get("output_shape")
            if not isinstance(output_shape, list):
                output_shape = []
            suffix = f", defined={definition_location}" if definition_location else ""
            print(
                f"  - {word_name}: pops={pops}, pushes={pushes}, effect={effect_kind}, host={host_surface}, output_shape={output_shape}{suffix}"
            )

    pocketcoder_host_words = analysis.get("pocketcoder_host_words_used", [])
    if isinstance(pocketcoder_host_words, list) and pocketcoder_host_words:
        print("")
        print("PocketCoder Host Dependencies:")
        for word_name in pocketcoder_host_words:
            print(f"  - {word_name}")

    if details.get("warning_count"):
        print("")
        print("Warnings:")
        for warning in details.get("warnings", []):
            code = warning.get("code") or "warning"
            location = warning.get("location")
            message = warning.get("message") or ""
            prefix = f"{code} ({location})" if location else str(code)
            print(f"  - {prefix}: {message}")

    if details.get("diagnostic_count"):
        print("")
        print("Diagnostics:")
        for diagnostic in details.get("diagnostics", []):
            code = diagnostic.get("code") or "diagnostic"
            location = diagnostic.get("location")
            authored_location = diagnostic.get("authored_location")
            message = diagnostic.get("message") or ""
            severity = diagnostic.get("severity") or "warning"
            prefix = f"{severity} {code}"
            if location:
                prefix = f"{prefix} ({location})"
            if authored_location:
                prefix = f"{prefix} [authored: {authored_location}]"
            print(f"  - {prefix}: {message}")

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
        _print_stackvm_update_warnings(updated.get("warnings"))
        return None

    if kind == "script":
        updated = engine.update_stackvm_script(target, source_text=text)
        print(f"Updated StackVM script '{updated['name']}' from {source_file} into {updated['path']}.")
        _print_stackvm_update_warnings(updated.get("warnings"))
        return None

    print("Usage: /stackvm alter <flow|script|agent> <name_or_path> <source_file>")
    return None


def _print_stackvm_stdlib_list(engine: Any) -> None:
    print("StackVM stdlib:")
    manifest = engine.get_stackvm_stdlib_manifest()
    print(f"  Package      : {manifest.get('package') or 'stackvm-stdlib'}")
    print(f"  Version      : {manifest.get('version') or 'unversioned'}")
    print(f"  Module root  : {manifest.get('module_root') or 'vm/stdlib'}")
    modules = engine.list_stackvm_stdlib_modules()
    if not modules:
        print("  Modules      : (none)")
        return
    print("  Modules:")
    for item in modules:
        name = item.get("name") or "(unnamed)"
        summary = item.get("summary") or ""
        exports = item.get("exports") or []
        dependencies = item.get("dependencies") or []
        print(f"    - {name}: {summary}")
        print(f"      ref={item.get('ref')}, exports={len(exports)}, dependencies={len(dependencies)}")


def _handle_stackvm_stdlib(args: list[str], engine: Any) -> Optional[str]:
    action = args[0].lower() if args else "list"
    if action == "list":
        _print_stackvm_stdlib_list(engine)
        return None
    if action == "check":
        report = engine.validate_stackvm_stdlib_manifest()
        print(f"StackVM stdlib check: {report.get('package')} {report.get('version')}")
        print(f"  Module root  : {report.get('module_root')}")
        print(f"  Modules      : {report.get('module_count', 0)}")
        print(f"  Warnings     : {report.get('warning_count', 0)}")
        print(f"  Errors       : {report.get('error_count', 0)}")
        print(f"  Valid        : {'yes' if report.get('valid') else 'no'}")
        modules = report.get("modules", [])
        if isinstance(modules, list) and modules:
            print("")
            print("Modules:")
            for item in modules:
                if not isinstance(item, dict):
                    continue
                print(f"  - {item.get('name')}: {'ok' if item.get('valid') else 'invalid'}")
                for warning in item.get("warnings", []):
                    print(f"    warning: {warning}")
                for error in item.get("errors", []):
                    print(f"    error: {error}")
        return None
    if action == "show":
        if len(args) < 2:
            print("Usage: /stackvm stdlib show <module_name>")
            return None
        target = str(args[1]).strip()
        modules = engine.list_stackvm_stdlib_modules()
        module = next((item for item in modules if str(item.get("name") or "").strip() == target), None)
        if module is None:
            print(f"Unknown StackVM stdlib module: {target}")
            return None
        print(f"StackVM stdlib module: {module.get('name')}")
        print(f"  Ref      : {module.get('ref')}")
        print(f"  File     : {module.get('file')}")
        print(f"  Summary  : {module.get('summary')}")
        print(f"  Exports  : {module.get('exports') or []}")
        print(f"  Dependencies: {module.get('dependencies') or []}")
        return None
    print("Usage: /stackvm stdlib [list|show <module_name>|check]")
    return None


def _group_shape_flow(shape_flow: list[Any]) -> Dict[str, list[dict[str, Any]]]:
    grouped: Dict[str, list[dict[str, Any]]] = {}
    for raw_step in shape_flow:
        if not isinstance(raw_step, dict):
            continue
        scope = str(raw_step.get("scope") or "main")
        grouped.setdefault(scope, []).append(raw_step)
    return grouped


def _print_stackvm_update_warnings(warnings: Any) -> None:
    if not isinstance(warnings, list) or not warnings:
        return
    print(f"  Warnings: {len(warnings)}")
    for item in warnings:
        if not isinstance(item, dict):
            continue
        code = item.get("code") or "warning"
        location = item.get("location")
        message = item.get("message") or ""
        prefix = f"{code} ({location})" if location else str(code)
        print(f"    - {prefix}: {message}")


def _group_runtime_trace(trace: list[Any]) -> Dict[str, list[dict[str, Any]]]:
    grouped: Dict[str, list[dict[str, Any]]] = {}
    for raw_step in trace:
        if not isinstance(raw_step, dict):
            continue
        scope = str(raw_step.get("scope") or "main")
        grouped.setdefault(scope, []).append(raw_step)
    return grouped


def _index_static_scope_summaries(analysis: dict[str, Any]) -> Dict[str, dict[str, Any]]:
    indexed: Dict[str, dict[str, Any]] = {}
    scope_summaries = analysis.get("scope_summaries", [])
    if not isinstance(scope_summaries, list):
        return indexed
    for item in scope_summaries:
        if not isinstance(item, dict):
            continue
        scope = str(item.get("scope") or "").strip()
        kind = str(item.get("kind") or "region")
        if not scope or kind != "region":
            continue
        indexed[scope] = item
    return indexed


def _index_static_shape_flow(analysis: dict[str, Any]) -> Dict[tuple[str, str], dict[str, Any]]:
    indexed: Dict[tuple[str, str], dict[str, Any]] = {}
    shape_flow = analysis.get("shape_flow", [])
    if not isinstance(shape_flow, list):
        return indexed
    for item in shape_flow:
        if not isinstance(item, dict):
            continue
        scope = str(item.get("scope") or "").strip()
        for location_key in ("location", "authored_location"):
            location = str(item.get(location_key) or "").strip()
            if scope and location:
                indexed[(scope, location)] = item
    return indexed


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
    last_vm_analysis = result.get("last_vm_analysis", {})
    if not isinstance(last_vm_analysis, dict):
        last_vm_analysis = {}
    static_scope_index = _index_static_scope_summaries(last_vm_analysis)
    static_shape_index = _index_static_shape_flow(last_vm_analysis)

    print(f"StackVM run complete for {kind} '{target}'.")
    if result.get("error_message"):
        print(f"  Error   : {result['error_message']}")
    print(f"  Output  : {result.get('output') or ''}")
    print(f"  Warnings: {result.get('run_summary', {}).get('vm_validation_warning_count', 0)}")
    print(f"  Diagnostics: {result.get('run_summary', {}).get('vm_diagnostic_count', 0)}")
    print(
        f"  Effects : {', '.join(result.get('run_summary', {}).get('vm_effect_kinds', []) or []) or '(none)'}"
    )
    print(f"  Final shape: {result.get('run_summary', {}).get('vm_final_stack_shape', [])}")
    runtime_summary = result.get("run_summary", {}).get("stackvm_runtime")
    if isinstance(runtime_summary, dict):
        print(
            f"  Runtime : {runtime_summary.get('path') or 'unknown'} "
            f"(source={runtime_summary.get('source') or 'unknown'})"
        )
    standalone_session = result.get("run_summary", {}).get("standalone_session")
    if isinstance(standalone_session, dict) and standalone_session.get("active"):
        print(f"  Session : {standalone_session.get('session_id')}")
        if standalone_session.get("title"):
            print(f"  Session title: {standalone_session.get('title')}")
        print(
            f"  Transcript: {standalone_session.get('transcript_entries', 0)} entr"
            f"{'y' if int(standalone_session.get('transcript_entries', 0) or 0) == 1 else 'ies'}"
            f", {standalone_session.get('transcript_chars', 0)} char(s)"
        )
        print(f"  Session keys: {standalone_session.get('persistent_key_count', 0)}")
    if result.get("tool_history"):
        print(f"  Tools   : {len(result['tool_history'])} call(s)")
    if debug:
        print(f"  Trace   : {result.get('trace_count', 0)} step(s)")
        if isinstance(runtime_summary, dict):
            print("")
            print("Runtime Provenance:")
            print(
                f"  - path={runtime_summary.get('path') or 'unknown'}, "
                f"source={runtime_summary.get('source') or 'unknown'}, "
                f"standalone_session_active={bool(runtime_summary.get('standalone_session_active'))}"
            )
        correlation = result.get("run_summary", {}).get("stackvm_static_runtime_correlation")
        if isinstance(correlation, dict):
            print("")
            print("Static/Runtime Correlation:")
            print(
                f"  - scopes: matched={correlation.get('matched_scope_count', 0)}/"
                f"{correlation.get('runtime_scope_count', 0)} runtime, "
                f"static={correlation.get('static_scope_count', 0)}"
            )
            print(
                f"  - decisions: matched={correlation.get('matched_decision_scope_count', 0)}/"
                f"{correlation.get('runtime_decision_scope_count', 0)} runtime, "
                f"static={correlation.get('static_decision_scope_count', 0)}"
            )
            runtime_only_scopes = correlation.get("runtime_only_scopes") or []
            static_only_scopes = correlation.get("static_only_scopes") or []
            if runtime_only_scopes:
                print(f"  - runtime_only_scopes={runtime_only_scopes}")
            if static_only_scopes:
                print(f"  - static_only_scopes={static_only_scopes}")
        if isinstance(standalone_session, dict) and standalone_session.get("active"):
            print("")
            print("Standalone Session:")
            print(f"  - id={standalone_session.get('session_id')}")
            if standalone_session.get("title"):
                print(f"  - title={standalone_session.get('title')}")
            print(
                f"  - transcript_entries={standalone_session.get('transcript_entries', 0)}, "
                f"transcript_chars={standalone_session.get('transcript_chars', 0)}, "
                f"persistent_keys={standalone_session.get('persistent_key_count', 0)}"
            )
        decisions = result.get("run_summary", {}).get("vm_trace_decisions", [])
        if isinstance(decisions, list) and decisions:
            print("")
            print("Runtime Decisions:")
            for item in decisions:
                if not isinstance(item, dict):
                    continue
                scope = item.get("scope") or "main"
                value = f", value={item.get('value')}" if "value" in item else ""
                print(
                    f"  - {scope}: {item.get('decision')} - {item.get('detail')}{value}"
                )
        scope_summaries = result.get("run_summary", {}).get("vm_trace_scope_summaries", [])
        if isinstance(scope_summaries, list) and scope_summaries:
            print("")
            print("Runtime Scope Summaries:")
            for item in scope_summaries:
                if not isinstance(item, dict):
                    continue
                scope = item.get("scope") or "main"
                static_scope = static_scope_index.get(str(scope))
                location = item.get("location")
                authored_location = item.get("authored_location")
                suffix = f" @ {location}" if location else ""
                if authored_location:
                    suffix += f" [authored: {authored_location}]"
                static_suffix = ""
                if isinstance(static_scope, dict):
                    static_suffix = (
                        f" static_out={static_scope.get('output_stack_shape', [])} "
                        f"static_effects={static_scope.get('effect_kinds', []) or []} "
                        f"static_shape_preserved={bool(static_scope.get('shape_preserved'))}"
                    )
                print(
                    f"  - {scope}{suffix}: "
                    f"in={item.get('input_stack')} "
                    f"delta={item.get('stack_delta')} "
                    f"out={item.get('output_stack')} "
                    f"shape_preserved={item.get('shape_preserved')}{static_suffix}"
                )
        if result.get("trace"):
            print("")
            print("Trace:")
            for scope_name, steps in _group_runtime_trace(result["trace"]).items():
                print(f"  {scope_name}:")
                for index, item in enumerate(steps, start=1):
                    op = item.get("op")
                    detail = item.get("word") if item.get("word") else item.get("value")
                    location = item.get("location")
                    authored_location = item.get("authored_location")
                    static_step = None
                    if location:
                        static_step = static_shape_index.get((str(scope_name), str(location)))
                    if static_step is None and authored_location:
                        static_step = static_shape_index.get((str(scope_name), str(authored_location)))
                    suffix = f" @ {location}" if location else ""
                    if authored_location:
                        suffix += f" [authored: {authored_location}]"
                    static_suffix = ""
                    if isinstance(static_step, dict):
                        static_suffix = f" static_shape={static_step.get('stack_shape', [])}"
                    print(
                        f"    {index:02d}. {op}: {detail} "
                        f"before={item.get('stack_before')} "
                        f"delta={item.get('stack_delta')} "
                        f"after={item.get('stack_after')}{suffix}{static_suffix}"
                    )
        print("")
        print("Expanded StackVM:")
        print(str(result.get("last_vm_expanded_source") or result.get("last_vm_source") or "").rstrip())
    return None


def print_stackvm_help() -> None:
    text = """
/stackvm Commands:
  /stackvm list [flows|scripts|stdlib]                   List registered StackVM flows, workspace scripts, and stdlib modules.
  /stackvm create flow <name> [--entry <word>] [--agent <agent_name>]
                                                         Create a StackVM-backed Markdown flow scaffold.
  /stackvm create script <name> [--entry <word>]         Create a standalone StackVM script under vm/.
/stackvm create agent <agent_name> <flow_name>         Create a workspace agent bound to a StackVM flow.
  /stackvm stdlib [list|show <module_name>|check]        Inspect or validate the shared StackVM stdlib manifest and modules.
  /stackvm inspect <flow|script|agent> <target> [--entry <word>]
                                                         Show compiled StackVM metadata, warnings, and expanded source.
  /stackvm check <flow|script|agent> <target> [--entry <word>]
                                                         Run static StackVM compilation and analysis without execution.
  /stackvm explain <flow|script|agent> <target> [--entry <word>]
                                                         Show macro expansion, inferred contracts, diagnostics, and expanded source.
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
