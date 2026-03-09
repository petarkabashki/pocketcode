from pocketflow import Flow, Node


class _EscalateNode(Node):
    def prep(self, shared):
        normalized = shared.get("normalized", {})
        return (
            normalized.get("summary", "unknown"),
            normalized.get("delegate_note", "no note"),
            normalized.get("delegate_source", "unspecified"),
        )

    def exec(self, payload):
        return payload

    def post(self, shared, prep_res, exec_res):
        summary, note, source = exec_res
        shared["final_answer"] = f"escalated nested route handled: {summary} | note={note} | delegate_source={source}"
        return "final_answer"


def create_flow():
    return Flow(start=_EscalateNode())
