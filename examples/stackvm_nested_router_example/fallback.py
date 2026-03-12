from pocketflow import Flow, Node


class _FallbackNode(Node):
    def prep(self, shared):
        return shared.get("route_reason", "nested fallback")

    def exec(self, reason):
        return reason

    def post(self, shared, prep_res, exec_res):
        shared["final_answer"] = f"nested fallback handled: {exec_res}"
        return "final_answer"


def create_flow():
    return Flow(start=_FallbackNode())