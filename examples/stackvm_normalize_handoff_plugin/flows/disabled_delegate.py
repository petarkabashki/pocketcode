from pocketflow import Flow, Node


class _DisabledNode(Node):
    def prep(self, shared):
        return shared.get("normalized", {}).get("summary", "unknown")

    def exec(self, summary):
        return summary

    def post(self, shared, prep_res, exec_res):
        shared["final_answer"] = f"disabled delegate handled: {exec_res}"
        return "final_answer"


def create_flow():
    return Flow(start=_DisabledNode())