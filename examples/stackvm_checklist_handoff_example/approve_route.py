from pocketflow import Flow, Node


class _ApproveNode(Node):
    def prep(self, shared):
        normalized = shared.get("normalized", {})
        return (
            normalized.get("summary", "unknown"),
            normalized.get("selected_actions_text", "unknown"),
        )

    def exec(self, payload):
        return payload

    def post(self, shared, prep_res, exec_res):
        summary, actions = exec_res
        shared["final_answer"] = f"approve route handled: {summary} with actions {actions}"
        return "final_answer"


def create_flow():
    return Flow(start=_ApproveNode())