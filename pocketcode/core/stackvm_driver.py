from __future__ import annotations

import asyncio
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from pocketcode.core.agent_stack_vm import AgentStackVM, StackVmExecutionResult
from pocketcode.core.runtime_observability import build_runtime_observability_summary
from pocketcode.core.stackvm_expander import expand_stackvm_source
from pocketcode.core.stackvm_host import StackVmHostContext, StandaloneStackVmHostAdapter
from pocketcode.core.stackvm_loader import load_stackvm_program_source
from pocketcode.core.stackvm_parser import (
    StackVmAstSpan,
    parse_stackvm_source,
    parse_stackvm_source_with_spans,
    serialize_stackvm_ast,
    tokenize_stackvm_source,
)
from pocketcode.core.stackvm_validator import analyze_stackvm_ast, collect_stackvm_authoring_warnings, validate_stackvm_ast


@dataclass(frozen=True)
class CompiledStackVmProgram:
    source: str
    source_files: list[str]
    entry: str | None
    expanded_source: str
    expanded_ast: list[Any]
    expanded_source_spans: list[StackVmAstSpan]
    authored_spans: list[StackVmAstSpan]
    warnings: list[dict[str, Any]]
    warning_count: int
    diagnostics: list[dict[str, Any]]
    diagnostic_count: int
    effect_kinds: list[str]
    max_stack_depth: int
    final_min_stack_depth: int
    analysis: dict[str, Any]
    expansion_metadata: dict[str, Any]
    token_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "expanded_source_spans",
            [_coerce_ast_span(item) for item in list(self.expanded_source_spans)],
        )
        object.__setattr__(
            self,
            "authored_spans",
            [_coerce_ast_span(item) for item in list(self.authored_spans)],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StandaloneStackVmRunResult:
    agent_name: str
    request: str
    output: str
    final_answer: Any
    question_to_ask: Any
    error_message: Any
    run_summary: dict[str, Any]
    trace: list[Any]
    trace_count: int
    last_vm_source: str
    last_vm_expanded_source: str
    last_vm_sources: list[str]
    last_vm_expansion_metadata: dict[str, Any]
    last_vm_validation_warnings: list[dict[str, Any]]
    last_vm_analysis: dict[str, Any]
    last_vm_diagnostics: list[dict[str, Any]]
    pending_tool: Any
    last_tool_result: Any
    tool_history: list[Any]
    pending_handoff_agent: Any
    results: dict[str, Any]
    shared_store: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "request": self.request,
            "output": self.output,
            "final_answer": self.final_answer,
            "question_to_ask": self.question_to_ask,
            "error_message": self.error_message,
            "run_summary": dict(self.run_summary),
            "trace": list(self.trace),
            "trace_count": self.trace_count,
            "last_vm_source": self.last_vm_source,
            "last_vm_expanded_source": self.last_vm_expanded_source,
            "last_vm_sources": list(self.last_vm_sources),
            "last_vm_expansion_metadata": dict(self.last_vm_expansion_metadata),
            "last_vm_validation_warnings": list(self.last_vm_validation_warnings),
            "last_vm_analysis": dict(self.last_vm_analysis),
            "last_vm_diagnostics": list(self.last_vm_diagnostics),
            "pending_tool": self.pending_tool,
            "last_tool_result": self.last_tool_result,
            "tool_history": list(self.tool_history),
            "pending_handoff_agent": self.pending_handoff_agent,
            "results": dict(self.results),
            "shared_store": self.shared_store,
        }


@dataclass(frozen=True)
class StackVmStandaloneHostConfig:
    interaction_handler: Any = None
    runtime_event_handler: Any = None
    llm_router: Any = None
    tool_runtime: Any = None
    llm_profile: str | None = None
    system_prompt: str = ""
    tool_definitions: list[dict[str, Any]] = field(default_factory=list)
    auto_confirm_tools: bool = False


def build_stackvm_standalone_host_config(
    *,
    interaction_handler: Any = None,
    runtime_event_handler: Any = None,
    llm_router: Any = None,
    tool_runtime: Any = None,
    llm_profile: str | None = None,
    system_prompt: str = "",
    tool_definitions: list[dict[str, Any]] | None = None,
    auto_confirm_tools: bool = False,
) -> StackVmStandaloneHostConfig:
    definitions = list(tool_definitions or [])
    if not definitions and tool_runtime is not None and hasattr(tool_runtime, "describe_tools"):
        tool_names = sorted(getattr(tool_runtime, "tools", {}).keys()) if hasattr(tool_runtime, "tools") else []
        definitions = list(tool_runtime.describe_tools(tool_names)) if tool_names else []
    return StackVmStandaloneHostConfig(
        interaction_handler=interaction_handler,
        runtime_event_handler=runtime_event_handler,
        llm_router=llm_router,
        tool_runtime=tool_runtime,
        llm_profile=llm_profile,
        system_prompt=str(system_prompt or ""),
        tool_definitions=definitions,
        auto_confirm_tools=bool(auto_confirm_tools),
    )


def _resolve_standalone_host_config(
    *,
    host_config: StackVmStandaloneHostConfig | None,
    interaction_handler: Any,
    runtime_event_handler: Any,
    llm_router: Any,
    tool_runtime: Any,
    llm_profile: str | None,
    system_prompt: str,
    tool_definitions: list[dict[str, Any]] | None,
    auto_confirm_tools: bool,
) -> StackVmStandaloneHostConfig:
    if host_config is None:
        return build_stackvm_standalone_host_config(
            interaction_handler=interaction_handler,
            runtime_event_handler=runtime_event_handler,
            llm_router=llm_router,
            tool_runtime=tool_runtime,
            llm_profile=llm_profile,
            system_prompt=str(system_prompt or ""),
            tool_definitions=list(tool_definitions or []),
            auto_confirm_tools=bool(auto_confirm_tools),
        )

    return build_stackvm_standalone_host_config(
        interaction_handler=interaction_handler if interaction_handler is not None else host_config.interaction_handler,
        runtime_event_handler=(
            runtime_event_handler if runtime_event_handler is not None else host_config.runtime_event_handler
        ),
        llm_router=llm_router if llm_router is not None else host_config.llm_router,
        tool_runtime=tool_runtime if tool_runtime is not None else host_config.tool_runtime,
        llm_profile=llm_profile if llm_profile is not None else host_config.llm_profile,
        system_prompt=str(system_prompt or host_config.system_prompt or ""),
        tool_definitions=list(tool_definitions or host_config.tool_definitions or []),
        auto_confirm_tools=bool(auto_confirm_tools or host_config.auto_confirm_tools),
    )


def _strip_signatures(ast: list[Any], spans: list[StackVmAstSpan]) -> tuple[list[Any], list[StackVmAstSpan]]:
    new_ast = []
    new_spans = []
    for node, span in zip(ast, spans):
        if isinstance(node, tuple) and node[0] == "sig":
            continue
        if isinstance(node, list):
            nested_ast, nested_spans = _strip_signatures(node, list(span.children))
            new_ast.append(nested_ast)
            new_spans.append(StackVmAstSpan(span=span.span, children=tuple(nested_spans)))
        else:
            new_ast.append(node)
            new_spans.append(span)
    return new_ast, new_spans


def compile_stackvm_program(
    *,
    source: str,
    source_files: list[str] | None = None,
    entry: str | None,
) -> CompiledStackVmProgram:
    compiled_source = str(source or "").strip()
    if not compiled_source and not entry:
        raise ValueError("StackVM target has no executable source or entry word.")

    warnings: list[dict[str, Any]] = []
    expanded_ast: list[Any] = []
    expanded_source = ""
    expanded_source_spans: list[StackVmAstSpan] = []
    authored_spans: list[StackVmAstSpan] = []
    expansion_metadata = {
        "expansion_count": 0,
        "macro_names": [],
        "builtin_macro_names": [],
        "gensym_count": 0,
        "expansion_trace": [],
        "expansion_frames": [],
    }
    token_count = 0
    analysis: dict[str, Any] = {
        "diagnostics": [],
        "diagnostic_count": 0,
        "effect_kinds": [],
        "max_stack_depth": 0,
        "final_min_stack_depth": 0,
        "word_metadata_summary": {},
    }

    if compiled_source:
        source_ast = parse_stackvm_source(compiled_source)
        token_count = len(tokenize_stackvm_source(compiled_source))
        warnings = collect_stackvm_authoring_warnings(source_ast, source=compiled_source)
        expanded = expand_stackvm_source(compiled_source)
        validate_stackvm_ast(expanded.ast)
        expanded_ast = expanded.ast
        authored_spans = list(expanded.ast_spans)
        expanded_source = serialize_stackvm_ast(expanded_ast) if expanded_ast else ""
        if expanded_source:
            _, expanded_source_spans = parse_stackvm_source_with_spans(expanded_source)
        analysis_ast = list(expanded.ast)
        if entry:
            analysis_ast.append(("sym", str(entry)))
        analysis = analyze_stackvm_ast(
            analysis_ast,
            source=serialize_stackvm_ast(analysis_ast),
            authored_spans=list(expanded.ast_spans),
        )
        
        stripped_ast, stripped_spans = _strip_signatures(expanded.ast, list(expanded.ast_spans))
        expanded_ast = stripped_ast
        authored_spans = stripped_spans
        expanded_source = serialize_stackvm_ast(expanded_ast) if expanded_ast else ""
        if expanded_source:
            _, expanded_source_spans = parse_stackvm_source_with_spans(expanded_source)
            
        used_macro_names = list(dict.fromkeys(expanded.expansion_trace))
        builtin_macro_names = [
            name
            for name in used_macro_names
            if name in expanded.macros and expanded.macros[name].builtin
        ]
        expansion_metadata = {
            "expansion_count": expanded.expansion_count,
            "macro_names": used_macro_names,
            "builtin_macro_names": builtin_macro_names,
            "gensym_count": expanded.gensym_count,
            "expansion_trace": list(expanded.expansion_trace),
            "expansion_frames": [
                {
                    "macro_name": frame.macro_name,
                    "builtin": frame.builtin,
                    "depth": frame.depth,
                    "call_site": frame.call_site,
                    "definition_site": frame.definition_site,
                    "generated_by": frame.generated_by,
                    "syntax_args": list(frame.syntax_args),
                    "expanded_form": frame.expanded_form,
                }
                for frame in expanded.expansion_frames
            ],
        }

    return CompiledStackVmProgram(
        source=compiled_source,
        source_files=list(source_files or []),
        entry=entry,
        expanded_source=expanded_source if compiled_source else "",
        expanded_ast=expanded_ast,
        expanded_source_spans=expanded_source_spans,
        authored_spans=authored_spans,
        warnings=warnings,
        warning_count=len(warnings),
        diagnostics=list(analysis.get("diagnostics", [])),
        diagnostic_count=int(analysis.get("diagnostic_count", 0)),
        effect_kinds=list(analysis.get("effect_kinds", [])),
        max_stack_depth=int(analysis.get("max_stack_depth", 0)),
        final_min_stack_depth=int(analysis.get("final_min_stack_depth", 0)),
        analysis=dict(analysis),
        expansion_metadata=expansion_metadata,
        token_count=token_count,
    )


def compile_stackvm_program_target(
    *,
    vm_source: str | None = None,
    vm_entry: str | None = None,
    vm_module: str | None = None,
    vm_modules: list[str] | tuple[str, ...] | None = None,
    vm_module_prefixes: dict[str, str] | None = None,
    vm_file: str | None = None,
    vm_files: list[str] | tuple[str, ...] | None = None,
    base_dir: str | Path | None = None,
    search_roots: list[str | Path] | tuple[str | Path, ...] = (),
) -> CompiledStackVmProgram:
    resolved_base_dir = Path(base_dir).resolve() if base_dir is not None else Path.cwd().resolve()
    resolved_search_roots = [Path(root).resolve() for root in search_roots]
    source, source_files = load_stackvm_program_source(
        vm_source=vm_source,
        vm_entry=vm_entry,
        vm_module=vm_module,
        vm_modules=list(vm_modules or []),
        vm_module_prefixes=dict(vm_module_prefixes or {}),
        vm_file=vm_file,
        vm_files=list(vm_files or []),
        base_dir=resolved_base_dir,
        search_roots=resolved_search_roots,
    )
    return compile_stackvm_program(
        source=source,
        source_files=source_files,
        entry=vm_entry,
    )


def run_compiled_stackvm_program(
    *,
    compiled: CompiledStackVmProgram,
    request: str = "",
    workspace_root: str | Path | None = None,
    agent_name: str = "__stackvm_standalone__",
    debug: bool = False,
    host_config: StackVmStandaloneHostConfig | None = None,
    auto_confirm_tools: bool = False,
    interaction_handler: Any = None,
    runtime_event_handler: Any = None,
    llm_router: Any = None,
    tool_runtime: Any = None,
    llm_profile: str | None = None,
    system_prompt: str = "",
    tool_definitions: list[dict[str, Any]] | None = None,
    shared_store: dict[str, Any] | None = None,
) -> StandaloneStackVmRunResult:
    resolved_workspace_root = Path(workspace_root).resolve() if workspace_root is not None else Path.cwd().resolve()
    resolved_host = _resolve_standalone_host_config(
        host_config=host_config,
        interaction_handler=interaction_handler,
        runtime_event_handler=runtime_event_handler,
        llm_router=llm_router,
        tool_runtime=tool_runtime,
        llm_profile=llm_profile,
        system_prompt=system_prompt,
        tool_definitions=tool_definitions,
        auto_confirm_tools=auto_confirm_tools,
    )
    cli_context = {
        "files": set(),
        "folders": set(),
        "urls": set(),
        "snippets": {},
        "interface": "stackvm-standalone",
    }
    store = dict(shared_store or {})
    store.setdefault("run_id", uuid4().hex)
    store["initial_request"] = str(request or "")
    store["workspace_root"] = str(resolved_workspace_root)
    store["filesystem_root"] = str(resolved_workspace_root)
    store["cli_context"] = {
        "files": [],
        "folders": [],
        "urls": [],
        "snippets": {},
        "interface": "stackvm-standalone",
    }
    store["formatted_cli_context"] = ""
    store["active_agent"] = str(agent_name)
    store["active_flow"] = None
    store["stackvm_runtime_path"] = "standalone-script"
    store["stackvm_runtime_source"] = "standalone-vm"
    store["stackvm_trace_enabled"] = bool(debug)
    store["auto_confirm_tools"] = bool(resolved_host.auto_confirm_tools)
    store["last_vm_sources"] = list(compiled.source_files)
    store["last_vm_source"] = compiled.source
    store["last_vm_expanded_source"] = compiled.expanded_source
    store["last_vm_expansion_metadata"] = dict(compiled.expansion_metadata)
    store["last_vm_validation_warnings"] = list(compiled.warnings)
    store["last_vm_analysis"] = dict(compiled.analysis)
    store["last_vm_diagnostics"] = list(compiled.diagnostics)
    if callable(resolved_host.runtime_event_handler):
        store["runtime_event_handler"] = resolved_host.runtime_event_handler
    if callable(resolved_host.interaction_handler):
        store["interaction_handler"] = resolved_host.interaction_handler

    definitions = list(resolved_host.tool_definitions or [])

    result = StackVmExecutionResult(source_files=list(compiled.source_files))
    host_context = StackVmHostContext(
        agent_name=str(agent_name),
        llm_router=resolved_host.llm_router,
        tool_runtime=resolved_host.tool_runtime,
        llm_profile=resolved_host.llm_profile,
        system_prompt=str(resolved_host.system_prompt or ""),
        tool_definitions=definitions,
    )
    vm = AgentStackVM(shared_store=store)
    vm.register_host_words(
        host_adapter=StandaloneStackVmHostAdapter(
            shared_store=store,
            host_context=host_context,
            result=result,
        )
    )
    _execute_stackvm_ast(
        vm=vm,
        ast=list(compiled.expanded_ast),
        trace_spans=list(compiled.expanded_source_spans),
        authored_spans=list(compiled.authored_spans),
        entry=compiled.entry,
    )

    output = str(store.get("final_answer") or "")
    if not output and vm.stack:
        output = str(vm.stack[-1])
    store["final_output"] = output
    summary = _build_run_summary(store, cli_context)
    return StandaloneStackVmRunResult(
        agent_name=str(agent_name),
        request=str(request or ""),
        output=output,
        final_answer=store.get("final_answer"),
        question_to_ask=store.get("question_to_ask"),
        error_message=store.get("error_message"),
        run_summary=summary,
        trace=list(store.get("vm_trace", [])),
        trace_count=len(store.get("vm_trace", [])),
        last_vm_source=str(store.get("last_vm_source", "")),
        last_vm_expanded_source=str(store.get("last_vm_expanded_source", "")),
        last_vm_sources=list(store.get("last_vm_sources", [])),
        last_vm_expansion_metadata=dict(store.get("last_vm_expansion_metadata", {})),
        last_vm_validation_warnings=list(store.get("last_vm_validation_warnings", [])),
        last_vm_analysis=dict(store.get("last_vm_analysis", {}))
        if isinstance(store.get("last_vm_analysis"), dict)
        else {},
        last_vm_diagnostics=list(store.get("last_vm_diagnostics", [])),
        pending_tool=store.get("pending_tool"),
        last_tool_result=store.get("last_tool_result"),
        tool_history=list(store.get("tool_history", [])),
        pending_handoff_agent=store.get("pending_handoff_agent"),
        results=dict(store.get("results", {})) if isinstance(store.get("results"), dict) else {},
        shared_store=store,
    )


def run_stackvm_program(
    *,
    source: str,
    entry: str | None = None,
    source_files: list[str] | None = None,
    **kwargs: Any,
) -> StandaloneStackVmRunResult:
    compiled = compile_stackvm_program(source=source, source_files=source_files, entry=entry)
    return run_compiled_stackvm_program(compiled=compiled, **kwargs)


def run_stackvm_program_target(
    *,
    vm_source: str | None = None,
    vm_entry: str | None = None,
    vm_module: str | None = None,
    vm_modules: list[str] | tuple[str, ...] | None = None,
    vm_module_prefixes: dict[str, str] | None = None,
    vm_file: str | None = None,
    vm_files: list[str] | tuple[str, ...] | None = None,
    base_dir: str | Path | None = None,
    search_roots: list[str | Path] | tuple[str | Path, ...] = (),
    **kwargs: Any,
) -> StandaloneStackVmRunResult:
    compiled = compile_stackvm_program_target(
        vm_source=vm_source,
        vm_entry=vm_entry,
        vm_module=vm_module,
        vm_modules=vm_modules,
        vm_module_prefixes=vm_module_prefixes,
        vm_file=vm_file,
        vm_files=vm_files,
        base_dir=base_dir,
        search_roots=search_roots,
    )
    return run_compiled_stackvm_program(compiled=compiled, **kwargs)


def _build_run_summary(shared_store: dict[str, Any], cli_context: dict[str, Any]) -> dict[str, Any]:
    vm_validation_warnings = shared_store.get("last_vm_validation_warnings", [])
    if not isinstance(vm_validation_warnings, list):
        vm_validation_warnings = []
    vm_diagnostics = shared_store.get("last_vm_diagnostics", [])
    if not isinstance(vm_diagnostics, list):
        vm_diagnostics = []
    vm_analysis = shared_store.get("last_vm_analysis", {})
    if not isinstance(vm_analysis, dict):
        vm_analysis = {}
    standalone_session = _build_standalone_session_summary(shared_store)
    return {
        "agent_path": [],
        "current_agent": shared_store.get("active_agent"),
        "active_skills": [],
        "current_llm_profile": shared_store.get("last_llm_profile"),
        "current_llm_model": (
            shared_store.get("last_llm_generation", {}).get("model")
            if isinstance(shared_store.get("last_llm_generation"), dict)
            else None
        ),
        "llm_usage": dict(shared_store.get("llm_usage_totals", {}))
        if isinstance(shared_store.get("llm_usage_totals"), dict)
        else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "llm_cost_usd": float(shared_store.get("llm_cost_usd_total", 0.0)),
        "vm_validation_warnings": list(vm_validation_warnings),
        "vm_validation_warning_count": len(vm_validation_warnings),
        "vm_diagnostics": list(vm_diagnostics),
        "vm_diagnostic_count": len(vm_diagnostics),
        "vm_effect_kinds": list(vm_analysis.get("effect_kinds", [])) if isinstance(vm_analysis.get("effect_kinds"), list) else [],
        "vm_max_stack_depth": int(vm_analysis.get("max_stack_depth", 0) or 0),
        "vm_final_min_stack_depth": int(vm_analysis.get("final_min_stack_depth", 0) or 0),
        "vm_final_stack_shape": list(vm_analysis.get("final_stack_shape", []))
        if isinstance(vm_analysis.get("final_stack_shape"), list)
        else [],
        "vm_trace_scope_summaries": list(shared_store.get("vm_trace_scope_summaries", []))
        if isinstance(shared_store.get("vm_trace_scope_summaries"), list)
        else [],
        "vm_trace_decisions": list(shared_store.get("vm_trace_decisions", []))
        if isinstance(shared_store.get("vm_trace_decisions"), list)
        else [],
        "last_runtime_effect": shared_store.get("last_runtime_effect"),
        "last_vm_effect": shared_store.get("last_vm_effect"),
        "last_vm_transition": shared_store.get("last_vm_transition"),
        "runtime_effect_count": len(shared_store.get("runtime_effect_history", []))
        if isinstance(shared_store.get("runtime_effect_history"), list)
        else 0,
        "runtime_effect_history": shared_store.get("runtime_effect_history", []),
        "vm_effect_count": len(shared_store.get("vm_effect_history", []))
        if isinstance(shared_store.get("vm_effect_history"), list)
        else 0,
        "vm_effect_history": shared_store.get("vm_effect_history", []),
        "stackvm_runtime": _build_stackvm_runtime_summary(shared_store),
        "stackvm_static_runtime_correlation": _build_static_runtime_correlation(shared_store),
        "standalone_session": standalone_session,
        "context_stats": _build_context_stats(cli_context),
        **build_runtime_observability_summary(shared_store),
    }


def _build_context_stats(cli_context: dict[str, Any]) -> dict[str, int]:
    files = cli_context.get("files", set())
    folders = cli_context.get("folders", set())
    urls = cli_context.get("urls", set())
    snippets = cli_context.get("snippets", {})
    return {
        "files": len(files) if isinstance(files, (set, list, tuple)) else 0,
        "folders": len(folders) if isinstance(folders, (set, list, tuple)) else 0,
        "urls": len(urls) if isinstance(urls, (set, list, tuple)) else 0,
        "snippets": len(snippets) if isinstance(snippets, dict) else 0,
        "snippet_chars": sum(len(str(value)) for value in snippets.values()) if isinstance(snippets, dict) else 0,
    }


def _build_standalone_session_summary(shared_store: dict[str, Any]) -> dict[str, Any] | None:
    session_id = str(shared_store.get("standalone_session_id") or "").strip()
    if not session_id:
        return None
    transcript = shared_store.get("standalone_transcript", [])
    if not isinstance(transcript, list):
        transcript = []
    transcript_text = str(shared_store.get("standalone_transcript_text") or "")
    persistent_state_keys = shared_store.get("standalone_session_persistent_keys", [])
    if not isinstance(persistent_state_keys, list):
        persistent_state_keys = []
    return {
        "active": True,
        "session_id": session_id,
        "title": str(shared_store.get("standalone_session_title") or ""),
        "transcript_entries": len(transcript),
        "transcript_chars": len(transcript_text),
        "persistent_key_count": len(persistent_state_keys),
    }


def _build_stackvm_runtime_summary(shared_store: dict[str, Any]) -> dict[str, Any]:
    runtime_path = str(shared_store.get("stackvm_runtime_path") or "").strip()
    runtime_source = str(shared_store.get("stackvm_runtime_source") or "").strip()
    standalone_session_active = bool(str(shared_store.get("standalone_session_id") or "").strip())
    return {
        "path": runtime_path or "unknown",
        "source": runtime_source or "unknown",
        "standalone_session_active": standalone_session_active,
    }


def _build_static_runtime_correlation(shared_store: dict[str, Any]) -> dict[str, Any]:
    analysis = shared_store.get("last_vm_analysis", {})
    if not isinstance(analysis, dict):
        analysis = {}
    static_scope_summaries = analysis.get("scope_summaries", [])
    if not isinstance(static_scope_summaries, list):
        static_scope_summaries = []
    static_decisions = analysis.get("analysis_decisions", [])
    if not isinstance(static_decisions, list):
        static_decisions = []
    runtime_scope_summaries = shared_store.get("vm_trace_scope_summaries", [])
    if not isinstance(runtime_scope_summaries, list):
        runtime_scope_summaries = []
    runtime_decisions = shared_store.get("vm_trace_decisions", [])
    if not isinstance(runtime_decisions, list):
        runtime_decisions = []

    static_scopes = {
        str(item.get("scope"))
        for item in static_scope_summaries
        if isinstance(item, dict) and str(item.get("scope") or "").strip()
    }
    runtime_scopes = {
        str(item.get("scope"))
        for item in runtime_scope_summaries
        if isinstance(item, dict) and str(item.get("scope") or "").strip()
    }
    static_decision_scopes = {
        str(item.get("scope"))
        for item in static_decisions
        if isinstance(item, dict) and str(item.get("scope") or "").strip()
    }
    runtime_decision_scopes = {
        str(item.get("scope"))
        for item in runtime_decisions
        if isinstance(item, dict) and str(item.get("scope") or "").strip()
    }

    matched_scopes = sorted(static_scopes & runtime_scopes)
    runtime_only_scopes = sorted(runtime_scopes - static_scopes)
    static_only_scopes = sorted(static_scopes - runtime_scopes)
    matched_decision_scopes = sorted(static_decision_scopes & runtime_decision_scopes)
    runtime_only_decision_scopes = sorted(runtime_decision_scopes - static_decision_scopes)
    static_only_decision_scopes = sorted(static_decision_scopes - runtime_decision_scopes)

    return {
        "static_scope_count": len(static_scopes),
        "runtime_scope_count": len(runtime_scopes),
        "matched_scope_count": len(matched_scopes),
        "matched_scopes": matched_scopes,
        "runtime_only_scopes": runtime_only_scopes,
        "static_only_scopes": static_only_scopes,
        "static_decision_scope_count": len(static_decision_scopes),
        "runtime_decision_scope_count": len(runtime_decision_scopes),
        "matched_decision_scope_count": len(matched_decision_scopes),
        "matched_decision_scopes": matched_decision_scopes,
        "runtime_only_decision_scopes": runtime_only_decision_scopes,
        "static_only_decision_scopes": static_only_decision_scopes,
    }


def _coerce_ast_span(value: Any) -> StackVmAstSpan:
    if isinstance(value, StackVmAstSpan):
        return value
    if isinstance(value, dict):
        span = value.get("span") or {}
        children = value.get("children") or ()
        return StackVmAstSpan(
            span=_coerce_source_span(span),
            children=tuple(_coerce_ast_span(child) for child in children),
        )
    raise TypeError(f"Unsupported StackVM AST span payload: {type(value)!r}")


def _coerce_source_span(value: Any) -> Any:
    if hasattr(value, "location"):
        return value
    if isinstance(value, dict):
        from pocketcode.core.stackvm_parser import StackVmSourceSpan

        return StackVmSourceSpan(
            start_line=int(value.get("start_line", 0) or 0),
            start_column=int(value.get("start_column", 0) or 0),
            end_line=int(value.get("end_line", 0) or 0),
            end_column=int(value.get("end_column", 0) or 0),
        )
    raise TypeError(f"Unsupported StackVM source span payload: {type(value)!r}")


def _execute_stackvm_ast(
    *,
    vm: AgentStackVM,
    ast: list[Any],
    trace_spans: list[StackVmAstSpan] | None,
    authored_spans: list[StackVmAstSpan] | None,
    entry: str | None,
) -> None:
    async def _runner() -> None:
        if ast:
            await vm.execute_ast(ast, trace_spans=trace_spans, authored_spans=authored_spans)
        if entry:
            await vm.execute_word(str(entry))

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_runner())
        return

    thread_error: dict[str, BaseException] = {}

    def _thread_runner() -> None:
        try:
            asyncio.run(_runner())
        except BaseException as exc:  # pragma: no cover
            thread_error["exc"] = exc

    worker = threading.Thread(target=_thread_runner, name="stackvm-standalone-driver")
    worker.start()
    worker.join()
    if "exc" in thread_error:
        raise thread_error["exc"]


from pocketcode.core.stackvm_standalone_runtime import (  # noqa: E402
    StackVmStandaloneRuntime,
    StackVmStandaloneSession,
    create_stackvm_standalone_runtime,
    create_stackvm_standalone_runtime_target,
    create_stackvm_standalone_session,
    create_stackvm_standalone_session_target,
    restore_stackvm_standalone_session,
    restore_stackvm_standalone_session_target,
)
