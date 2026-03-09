from pocketflow import Flow, Node


class _EscalateNode(Node):
    def prep(self, shared):
        normalized = shared.get("normalized", {})
        return (
            normalized.get("summary", "unknown"),
            normalized.get("delegate_note", "no note"),
        )

    def exec(self, payload):
        return payload

    def post(self, shared, prep_res, exec_res):
        summary, note = exec_res
        shared["final_answer"] = f"escalated route handled: {summary} ({note})"
        return "final_answer"


def create_flow():
    return Flow(start=_EscalateNode())
