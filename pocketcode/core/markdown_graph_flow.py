from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, List, Tuple

from pocketflow import Flow, Node


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    transition: str = "default"


def build_graph_flow_from_metadata(definition: Dict[str, Any]) -> Flow | None:
    metadata = definition.get("metadata") or {}
    graphs = metadata.get("markdown_graphs") or []
    if not isinstance(graphs, list) or not graphs:
        return None

    nodes_spec = definition.get("nodes") or {}
    if not isinstance(nodes_spec, dict):
        nodes_spec = {}

    start_node = str(definition.get("start") or "").strip() or None
    for graph in graphs:
        if not isinstance(graph, dict):
            continue
        language = str(graph.get("language") or "").strip().lower()
        content = str(graph.get("content") or "").strip()
        if not content:
            continue
        if language == "mermaid":
            return build_graph_flow_from_mermaid(content, nodes_spec=nodes_spec, start_node=start_node)
        if language == "dot":
            return build_graph_flow_from_dot(content, nodes_spec=nodes_spec, start_node=start_node)
    return None


def build_graph_flow_from_mermaid(
    graph_text: str,
    *,
    nodes_spec: Dict[str, Any] | None = None,
    start_node: str | None = None,
) -> Flow:
    nodes, edges = parse_mermaid_graph(graph_text)
    return build_graph_flow(
        node_ids=nodes,
        edges=edges,
        nodes_spec=nodes_spec or {},
        start_node=start_node,
    )


def build_graph_flow_from_dot(
    graph_text: str,
    *,
    nodes_spec: Dict[str, Any] | None = None,
    start_node: str | None = None,
) -> Flow:
    nodes, edges = parse_dot_graph(graph_text)
    return build_graph_flow(
        node_ids=nodes,
        edges=edges,
        nodes_spec=nodes_spec or {},
        start_node=start_node,
    )


def build_graph_flow(
    *,
    node_ids: Iterable[str],
    edges: Iterable[GraphEdge],
    nodes_spec: Dict[str, Any],
    start_node: str | None,
) -> Flow:
    ordered_nodes = [node_id for node_id in node_ids if str(node_id).strip()]
    if not ordered_nodes:
        raise ValueError("Graph flow must define at least one node.")

    edge_list = list(edges)
    _validate_graph_node_specs(
        node_ids=ordered_nodes,
        edges=edge_list,
        nodes_spec=nodes_spec,
        start_node=start_node,
    )

    compiled_nodes: Dict[str, GraphFlowNode] = {}
    for node_id in ordered_nodes:
        raw_spec = nodes_spec.get(node_id, {}) if isinstance(nodes_spec, dict) else {}
        node_spec = dict(raw_spec) if isinstance(raw_spec, dict) else {}
        compiled_nodes[node_id] = GraphFlowNode(node_id=node_id, spec=node_spec)

    for edge in edge_list:
        if edge.source not in compiled_nodes or edge.target not in compiled_nodes:
            continue
        compiled_nodes[edge.source].next(compiled_nodes[edge.target], action=edge.transition)

    resolved_start = start_node or _infer_start_node(ordered_nodes, edge_list)
    if resolved_start not in compiled_nodes:
        raise ValueError(f"Graph flow start node '{resolved_start}' is not defined.")
    return Flow(start=compiled_nodes[resolved_start])


def _validate_graph_node_specs(
    *,
    node_ids: list[str],
    edges: list[GraphEdge],
    nodes_spec: Dict[str, Any],
    start_node: str | None,
) -> None:
    declared_nodes = set(node_ids)
    extra_specs = sorted(str(node_id) for node_id in nodes_spec.keys() if str(node_id) not in declared_nodes)
    if extra_specs:
        unknown = ", ".join(extra_specs)
        raise ValueError(f"Graph flow nodes spec declares nodes not present in the graph: {unknown}.")

    resolved_start = start_node or _infer_start_node(node_ids, edges)
    if resolved_start not in declared_nodes:
        raise ValueError(f"Graph flow start node '{resolved_start}' is not defined.")

    outgoing: Dict[str, set[str]] = {}
    for edge in edges:
        outgoing.setdefault(edge.source, set()).add(edge.transition)

    for node_id in node_ids:
        raw_spec = nodes_spec.get(node_id, {}) if isinstance(nodes_spec, dict) else {}
        node_spec = dict(raw_spec) if isinstance(raw_spec, dict) else {}
        _validate_graph_node_spec(node_id=node_id, spec=node_spec, outgoing_transitions=outgoing.get(node_id, set()))


def _validate_graph_node_spec(*, node_id: str, spec: Dict[str, Any], outgoing_transitions: set[str]) -> None:
    kind = str(spec.get("kind") or spec.get("type") or "route").strip().lower()
    if kind not in {"route", "branch", "decision", "noop", "pass", "set", "tool", "handoff", "output", "end", "answer", "ask"}:
        raise ValueError(f"Unsupported markdown graph node kind '{kind}' on '{node_id}'.")

    if kind in {"noop", "pass", "set"}:
        _validate_static_transition(
            node_id=node_id,
            transition=_static_transition_value(spec.get("transition") or spec.get("next") or "default"),
            outgoing_transitions=outgoing_transitions,
        )
        return

    if kind in {"route", "branch", "decision"}:
        _validate_static_transition(
            node_id=node_id,
            transition=_static_transition_value(spec.get("transition")),
            outgoing_transitions=outgoing_transitions,
        )
        _validate_static_transition(
            node_id=node_id,
            transition=_static_transition_value(spec.get("default_transition") or spec.get("default")),
            outgoing_transitions=outgoing_transitions,
        )
        _validate_transition_map(
            node_id=node_id,
            transition_map=spec.get("transition_map"),
            outgoing_transitions=outgoing_transitions,
        )
        return

    if kind == "tool":
        tool_name = spec.get("tool") or spec.get("name")
        if tool_name is None or not str(tool_name).strip():
            raise ValueError(f"Tool node '{node_id}' is missing 'tool'.")
        _validate_static_transition(
            node_id=node_id,
            transition=_static_transition_value(spec.get("success_transition")),
            outgoing_transitions=outgoing_transitions,
        )
        _validate_static_transition(
            node_id=node_id,
            transition=_static_transition_value(spec.get("failure_transition") or spec.get("error_transition")),
            outgoing_transitions=outgoing_transitions,
        )
        _validate_transition_map(
            node_id=node_id,
            transition_map=spec.get("result_transition_map"),
            outgoing_transitions=outgoing_transitions,
        )
        _validate_static_transition(
            node_id=node_id,
            transition=_static_transition_value(spec.get("transition") or spec.get("next")),
            outgoing_transitions=outgoing_transitions,
        )
        return

    if kind == "handoff":
        target = spec.get("agent") or spec.get("handoff") or spec.get("target")
        if target is None or not str(target).strip():
            raise ValueError(f"Handoff node '{node_id}' is missing 'agent'.")
        return

    if kind in {"output", "end", "answer", "ask"}:
        explicit_transition = _static_transition_value(spec.get("transition"))
        if explicit_transition is None:
            default_terminal = "ask_user" if str(spec.get("output_key") or "final_answer").strip() == "question_to_ask" else "final_answer"
            _validate_static_transition(
                node_id=node_id,
                transition=default_terminal,
                outgoing_transitions=outgoing_transitions,
            )
            return
        _validate_static_transition(
            node_id=node_id,
            transition=explicit_transition,
            outgoing_transitions=outgoing_transitions,
        )


def _validate_transition_map(*, node_id: str, transition_map: Any, outgoing_transitions: set[str]) -> None:
    if not isinstance(transition_map, dict):
        return
    for transition in transition_map.values():
        _validate_static_transition(
            node_id=node_id,
            transition=_static_transition_value(transition),
            outgoing_transitions=outgoing_transitions,
        )


def _validate_static_transition(*, node_id: str, transition: str | None, outgoing_transitions: set[str]) -> None:
    if transition is None or transition in {"final_answer", "ask_user", "handoff"}:
        return
    if transition not in outgoing_transitions:
        available = ", ".join(sorted(outgoing_transitions)) if outgoing_transitions else "<none>"
        raise ValueError(
            f"Graph node '{node_id}' references transition '{transition}' but outgoing graph edges are: {available}."
        )


def _static_transition_value(value: Any) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    if not candidate:
        return None
    if candidate.startswith("$") or "${" in candidate or "{{" in candidate:
        return None
    return candidate


class GraphFlowNode(Node):
    def __init__(self, *, node_id: str, spec: Dict[str, Any]):
        super().__init__()
        self.node_id = node_id
        self.spec = spec

    def _run(self, shared: Dict[str, Any]) -> str | None:
        kind = str(self.spec.get("kind") or self.spec.get("type") or "route").strip().lower()
        shared["active_node_id"] = self.node_id
        shared["active_node_kind"] = kind
        _emit_runtime_event(
            shared,
            "node_started",
            node_id=self.node_id,
            node_kind=kind,
            agent=shared.get("active_agent"),
        )
        context = {"shared": shared}
        _apply_updates(shared, self.spec.get("set") or self.spec.get("updates"), context=context)

        transition: str | None = None
        if kind in {"route", "branch", "decision"}:
            transition = _resolve_transition(shared, self.spec, context=context)
            _emit_runtime_event(
                shared,
                "node_completed",
                node_id=self.node_id,
                node_kind=kind,
                agent=shared.get("active_agent"),
                transition=transition,
            )
            return transition

        if kind in {"noop", "pass", "set"}:
            transition = str(_resolve_value(self.spec.get("transition") or self.spec.get("next") or "default", context))
            _emit_runtime_event(
                shared,
                "node_completed",
                node_id=self.node_id,
                node_kind=kind,
                agent=shared.get("active_agent"),
                transition=transition,
            )
            return transition

        if kind == "tool":
            transition = self._run_tool_node(shared)
            _emit_runtime_event(
                shared,
                "node_completed",
                node_id=self.node_id,
                node_kind=kind,
                agent=shared.get("active_agent"),
                transition=transition,
            )
            return transition

        if kind == "handoff":
            target = _resolve_value(self.spec.get("agent") or self.spec.get("handoff") or self.spec.get("target"), shared)
            if target:
                shared["pending_handoff_agent"] = str(target)
            context_mode = self.spec.get("context_mode") or self.spec.get("handoff_context_mode")
            if context_mode:
                shared["active_handoff_context_mode"] = str(context_mode)
            transition = "handoff"
            _emit_runtime_event(
                shared,
                "node_completed",
                node_id=self.node_id,
                node_kind=kind,
                agent=shared.get("active_agent"),
                transition=transition,
            )
            return transition

        if kind in {"output", "end", "answer", "ask"}:
            transition = self._run_output_node(shared)
            _emit_runtime_event(
                shared,
                "node_completed",
                node_id=self.node_id,
                node_kind=kind,
                agent=shared.get("active_agent"),
                transition=transition,
            )
            return transition

        raise ValueError(f"Unsupported markdown graph node kind '{kind}' on '{self.node_id}'.")

    def _run_tool_node(self, shared: Dict[str, Any]) -> str:
        context = {"shared": shared}
        tool_name = _resolve_value(self.spec.get("tool") or self.spec.get("name"), context)
        if not tool_name:
            raise ValueError(f"Tool node '{self.node_id}' is missing 'tool'.")

        tool_runtime = shared.get("_tool_runtime")
        if tool_runtime is None:
            raise ValueError(f"Tool node '{self.node_id}' requires '_tool_runtime' in shared state.")

        arguments = _resolve_value(self.spec.get("arguments") or {}, context)
        if not isinstance(arguments, dict):
            raise ValueError(f"Tool node '{self.node_id}' arguments must resolve to a mapping.")

        result = tool_runtime.execute_tool(
            str(tool_name),
            arguments,
            shared,
            agent_name=str(shared.get("active_agent") or "").strip() or None,
        )
        shared.setdefault("results", {})[self.node_id] = result
        shared["last_tool_result"] = result

        result_context = {"shared": shared, "result": result}

        result_key = str(self.spec.get("result_key") or "").strip()
        if result_key:
            shared[result_key] = result

        store_mapping = self.spec.get("store")
        resolved_store_mapping = _resolve_value(store_mapping, result_context)
        if isinstance(resolved_store_mapping, dict):
            for key, value in resolved_store_mapping.items():
                if str(key).strip():
                    shared[str(key)] = value

        if isinstance(result, dict) and result.get("success") is False:
            error_transition = str(
                _resolve_value(
                    self.spec.get("failure_transition") or self.spec.get("error_transition") or "error",
                    result_context,
                )
            )
            if result.get("error") and not shared.get("error_message"):
                shared["error_message"] = str(result["error"])
            return error_transition

        if self.spec.get("success_transition"):
            return str(_resolve_value(self.spec.get("success_transition"), result_context))

        if self.spec.get("result_transition_key"):
            resolved = _lookup_path(result, str(self.spec.get("result_transition_key")))
            if resolved is not None:
                transition_map = self.spec.get("result_transition_map")
                resolved_map = _resolve_value(transition_map, result_context)
                if isinstance(resolved_map, dict):
                    mapped = resolved_map.get(resolved)
                    if mapped is None:
                        mapped = resolved_map.get(str(resolved))
                    if mapped is not None:
                        return str(mapped)
                return str(resolved)

        return str(_resolve_value(self.spec.get("transition") or self.spec.get("next") or "default", result_context))

    def _run_output_node(self, shared: Dict[str, Any]) -> str:
        context = {"shared": shared}
        message = _resolve_value(
            self.spec.get("message")
            or self.spec.get("final_answer")
            or self.spec.get("question")
            or self.spec.get("output"),
            context,
        )
        output_key = str(self.spec.get("output_key") or "final_answer").strip() or "final_answer"
        if message is not None:
            shared[output_key] = str(message)

        transition = str(_resolve_value(self.spec.get("transition") or "", context)).strip().lower()
        if transition:
            return transition
        if output_key == "question_to_ask":
            return "ask_user"
        return "final_answer"


def parse_mermaid_graph(graph_text: str) -> tuple[list[str], list[GraphEdge]]:
    nodes: list[str] = []
    seen: set[str] = set()
    edges: list[GraphEdge] = []

    for raw_line in graph_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("%%"):
            continue
        lowered = line.lower()
        if lowered.startswith("graph ") or lowered.startswith("flowchart "):
            continue

        if "-->" in line:
            source_part, remainder = line.split("-->", 1)
            source = _clean_graph_node_token(source_part)
            transition = "default"
            target_part = remainder.strip()
            if target_part.startswith("|") and "|" in target_part[1:]:
                transition, target_part = target_part[1:].split("|", 1)
                transition = transition.strip() or "default"
            target = _clean_graph_node_token(target_part)
            if source:
                _append_once(nodes, seen, source)
            if target:
                _append_once(nodes, seen, target)
            if source and target:
                edges.append(GraphEdge(source=source, target=target, transition=transition))
            continue

        standalone = _clean_graph_node_token(line)
        if standalone:
            _append_once(nodes, seen, standalone)

    return nodes, edges


def parse_dot_graph(graph_text: str) -> tuple[list[str], list[GraphEdge]]:
    nodes: list[str] = []
    seen: set[str] = set()
    edges: list[GraphEdge] = []

    for raw_line in graph_text.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line or line in {"{", "}"} or line.startswith("digraph"):
            continue
        if line.endswith(";"):
            line = line[:-1].strip()

        if "->" in line:
            source_part, remainder = line.split("->", 1)
            source = _clean_dot_identifier(source_part)
            transition = "default"
            target_part = remainder.strip()
            if "[" in target_part and "]" in target_part:
                target_raw, attrs_raw = target_part.split("[", 1)
                target_part = target_raw.strip()
                attrs_body = attrs_raw.rsplit("]", 1)[0]
                transition = _extract_dot_transition(attrs_body)
            target = _clean_dot_identifier(target_part)
            if source:
                _append_once(nodes, seen, source)
            if target:
                _append_once(nodes, seen, target)
            if source and target:
                edges.append(GraphEdge(source=source, target=target, transition=transition))
            continue

        standalone = _clean_dot_identifier(line.split("[", 1)[0].strip())
        if standalone:
            _append_once(nodes, seen, standalone)

    return nodes, edges


def _append_once(nodes: list[str], seen: set[str], value: str) -> None:
    if value not in seen:
        seen.add(value)
        nodes.append(value)


def _clean_graph_node_token(token: str) -> str:
    cleaned = token.strip()
    for delimiter in ("[", "(", "{"):
        if delimiter in cleaned:
            cleaned = cleaned.split(delimiter, 1)[0].strip()
    return cleaned.strip('"\' ')


def _clean_dot_identifier(token: str) -> str:
    return token.strip().strip('"\' ')


def _extract_dot_transition(attrs_body: str) -> str:
    for chunk in attrs_body.split(","):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        if key.strip() in {"label", "transition", "condition"}:
            cleaned = value.strip().strip('"\' ')
            return cleaned or "default"
    return "default"


def _infer_start_node(node_ids: list[str], edges: list[GraphEdge]) -> str:
    targets = {edge.target for edge in edges}
    for node_id in node_ids:
        if node_id not in targets:
            return node_id
    return node_ids[0]


def _apply_updates(shared: Dict[str, Any], updates: Any, *, context: Dict[str, Any]) -> None:
    resolved = _resolve_value(updates, context)
    if isinstance(resolved, dict):
        shared.update(resolved)


def _resolve_transition(shared: Dict[str, Any], spec: Dict[str, Any], *, context: Dict[str, Any]) -> str:
    direct = spec.get("transition")
    if direct:
        return str(_resolve_value(direct, context))

    transition_key = str(spec.get("transition_key") or "transition").strip()
    value = _lookup_path(shared, transition_key)
    if value is not None and str(value).strip():
        transition_map = spec.get("transition_map")
        resolved_map = _resolve_value(transition_map, context)
        if isinstance(resolved_map, dict):
            mapped = resolved_map.get(value)
            if mapped is None:
                mapped = resolved_map.get(str(value))
            if mapped is not None:
                return str(mapped)
        return str(value)

    default_transition = spec.get("default_transition") or spec.get("default") or "default"
    return str(_resolve_value(default_transition, context))


def _emit_runtime_event(shared: Dict[str, Any], event_type: str, **payload: Any) -> None:
    handler = shared.get("runtime_event_handler")
    if callable(handler):
        handler(event_type, **payload)


_INTERPOLATION_PATTERNS = (
    re.compile(r"\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\.([^}]+?)\s*\}"),
    re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\.([^}]+?)\s*\}\}"),
)


def _resolve_value(value: Any, context: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        direct_lookup = _resolve_direct_lookup(stripped, context)
        if direct_lookup is not _MISSING:
            return direct_lookup
        return _interpolate_string(value, context)
    if isinstance(value, list):
        return [_resolve_value(item, context) for item in value]
    if isinstance(value, dict):
        return {str(key): _resolve_value(item, context) for key, item in value.items()}
    return value


_MISSING = object()


def _resolve_direct_lookup(value: str, context: Dict[str, Any]) -> Any:
    if value.startswith("$") and "." in value[1:]:
        scope, path = value[1:].split(".", 1)
        base = context.get(scope)
        if base is None:
            return _MISSING
        resolved = _lookup_path(base, path)
        return _MISSING if resolved is None else resolved
    return _MISSING


def _interpolate_string(template: str, context: Dict[str, Any]) -> str:
    rendered = template
    for pattern in _INTERPOLATION_PATTERNS:
        rendered = pattern.sub(lambda match: _replace_interpolation_match(match, context), rendered)
    return rendered


def _replace_interpolation_match(match: re.Match[str], context: Dict[str, Any]) -> str:
    scope = match.group(1).strip()
    path = match.group(2).strip()
    base = context.get(scope)
    if base is None:
        return ""
    resolved = _lookup_path(base, path)
    if resolved is None:
        return ""
    return str(resolved)


def _lookup_path(value: Any, path: str) -> Any:
    current = value
    for part in str(path or "").split("."):
        key = part.strip()
        if not key:
            continue
        if isinstance(current, dict) and key in current:
            current = current[key]
            continue
        return None
    return current
