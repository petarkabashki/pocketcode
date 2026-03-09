from pocketflow import Flow, Node


class _DelegateNode(Node):
    def prep(self, shared):
        return shared.get("route_message", "delegate")

    def exec(self, message):
        return message

    def post(self, shared, prep_res, exec_res):
        shared["final_answer"] = f"config delegate handled: {exec_res}"
        return "final_answer"


def create_flow():
    return Flow(start=_DelegateNode())