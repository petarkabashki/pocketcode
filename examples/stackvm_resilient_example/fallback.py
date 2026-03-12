from pocketflow import Flow, Node


class _FallbackNode(Node):
    def prep(self, shared):
        return shared.get("last_tool_result", {})

    def exec(self, tool_result):
        if isinstance(tool_result, dict):
            return tool_result.get("error") or "fallback"
        return "fallback"

    def post(self, shared, prep_res, exec_res):
        shared["final_answer"] = f"fallback handled tool failure: {exec_res}"
        return "final_answer"


def create_flow():
    return Flow(start=_FallbackNode())