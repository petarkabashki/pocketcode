from __future__ import annotations

from pocketcode.core.markdown_graph_flow import build_graph_flow_from_metadata


class _ToolRuntimeStub:
    def execute_tool(self, tool_name, arguments, shared_store, auto_confirm=False, agent_name=None):
        return {
            "success": True,
            "tool": tool_name,
            "message": f"echo:{arguments['text']}",
        }


class _BranchingToolRuntimeStub:
    def execute_tool(self, tool_name, arguments, shared_store, auto_confirm=False, agent_name=None):
        mode = arguments.get("mode")
        if mode == "fail":
            return {"success": False, "error": "tool failed", "status": "failed"}
        if mode == "warn":
            return {"success": True, "status": "warning", "message": "warned"}
        return {"success": True, "status": "ok", "message": f"done:{arguments.get('name', '')}"}


def test_mermaid_graph_flow_routes_to_output_nodes():
    definition = {
        "metadata": {
            "markdown_graphs": [
                {
                    "language": "mermaid",
                    "content": """
graph TD
  route -->|path_a| answer_a
  route -->|path_b| answer_b
""",
                }
            ]
        },
        "nodes": {
            "route": {"kind": "route", "transition_key": "requested_path"},
            "answer_a": {"kind": "output", "message": "Alpha"},
            "answer_b": {"kind": "output", "message": "Beta"},
        },
    }

    flow = build_graph_flow_from_metadata(definition)
    shared_a = {"requested_path": "path_a"}
    shared_b = {"requested_path": "path_b"}

    assert flow is not None
    assert flow.run(shared_a) == "final_answer"
    assert flow.run(shared_b) == "final_answer"
    assert shared_a["final_answer"] == "Alpha"
    assert shared_b["final_answer"] == "Beta"


def test_dot_graph_flow_executes_tool_node_and_uses_result_in_output():
    definition = {
        "metadata": {
            "markdown_graphs": [
                {
                    "language": "dot",
                    "content": """
digraph G {
  start -> call;
  call -> done;
}
""",
                }
            ]
        },
        "nodes": {
            "start": {"kind": "noop", "transition": "default"},
            "call": {
                "kind": "tool",
                "tool": "workspace.echo",
                "arguments": {"text": "$shared.user_text"},
                "result_key": "echo_result",
            },
            "done": {
                "kind": "output",
                "message": "$shared.echo_result.message",
            },
        },
    }

    flow = build_graph_flow_from_metadata(definition)
    shared = {
        "user_text": "hello",
        "_tool_runtime": _ToolRuntimeStub(),
        "active_agent": "graph.agent",
    }

    assert flow is not None
    assert flow.run(shared) == "final_answer"
    assert shared["echo_result"]["tool"] == "workspace.echo"
    assert shared["final_answer"] == "echo:hello"


def test_graph_flow_interpolates_strings_and_maps_tool_result_transitions():
    definition = {
        "metadata": {
            "markdown_graphs": [
                {
                    "language": "mermaid",
                    "content": """
graph TD
  call -->|ok_path| ok
  call -->|warn_path| warn
  call -->|failed_path| failed
""",
                }
            ]
        },
        "nodes": {
            "call": {
                "kind": "tool",
                "tool": "workspace.brancher",
                "arguments": {
                    "mode": "${shared.mode}",
                    "name": "{{ shared.user.name }}",
                },
                "result_key": "tool_result",
                "store": {
                    "tool_message": "${result.message}",
                },
                "failure_transition": "failed_path",
                "result_transition_key": "status",
                "result_transition_map": {
                    "ok": "ok_path",
                    "warning": "warn_path",
                },
            },
            "ok": {
                "kind": "output",
                "message": "OK for ${shared.user.name}: ${shared.tool_message}",
            },
            "warn": {
                "kind": "output",
                "message": "WARN for {{ shared.user.name }}: ${shared.tool_message}",
            },
            "failed": {
                "kind": "output",
                "message": "FAILED for ${shared.user.name}",
            },
        },
    }

    flow = build_graph_flow_from_metadata(definition)

    shared_ok = {
        "mode": "ok",
        "user": {"name": "Ada"},
        "_tool_runtime": _BranchingToolRuntimeStub(),
        "active_agent": "graph.agent",
    }
    shared_warn = {
        "mode": "warn",
        "user": {"name": "Ada"},
        "_tool_runtime": _BranchingToolRuntimeStub(),
        "active_agent": "graph.agent",
    }
    shared_fail = {
        "mode": "fail",
        "user": {"name": "Ada"},
        "_tool_runtime": _BranchingToolRuntimeStub(),
        "active_agent": "graph.agent",
    }

    assert flow is not None
    assert flow.run(shared_ok) == "final_answer"
    assert flow.run(shared_warn) == "final_answer"
    assert flow.run(shared_fail) == "final_answer"

    assert shared_ok["final_answer"] == "OK for Ada: done:Ada"
    assert shared_warn["final_answer"] == "WARN for Ada: warned"
    assert shared_fail["final_answer"] == "FAILED for Ada"
    assert shared_fail["error_message"] == "tool failed"


def test_graph_flow_rejects_static_transition_without_matching_edge():
    definition = {
        "metadata": {
            "markdown_graphs": [
                {
                    "language": "mermaid",
                    "content": """
graph TD
  start -->|ok| done
""",
                }
            ]
        },
        "nodes": {
            "start": {"kind": "noop", "transition": "missing"},
            "done": {"kind": "output", "message": "Done"},
        },
    }

    try:
        build_graph_flow_from_metadata(definition)
    except ValueError as exc:
        assert "references transition 'missing'" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing graph transition.")


def test_graph_flow_rejects_nodes_spec_not_present_in_graph():
    definition = {
        "metadata": {
            "markdown_graphs": [
                {
                    "language": "dot",
                    "content": """
digraph G {
  start -> done;
}
""",
                }
            ]
        },
        "nodes": {
            "start": {"kind": "noop", "transition": "default"},
            "done": {"kind": "output", "message": "Done"},
            "typo_done": {"kind": "output", "message": "Unused"},
        },
    }

    try:
        build_graph_flow_from_metadata(definition)
    except ValueError as exc:
        assert "nodes spec declares nodes not present in the graph" in str(exc)
    else:
        raise AssertionError("Expected ValueError for graph node spec typo.")