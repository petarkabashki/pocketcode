from pocketflow import Flow, Node


class _ReviewRouteNode(Node):
    def prep(self, shared):
        normalized = shared.get("normalized", {})
        return normalized.get("total", 0)

    def exec(self, total):
        return total

    def post(self, shared, prep_res, exec_res):
        shared["final_answer"] = f"review route handled total: {exec_res}"
        return "final_answer"


def create_flow():
    return Flow(start=_ReviewRouteNode())