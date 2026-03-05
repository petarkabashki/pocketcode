from pocketflow import Node, Flow

class HelloNode(Node):
    def prep(self, shared):
        print("HelloNode prep")
        return True
    
    def _run(self, shared):
        print("HelloNode _run")
        ctx = shared.get("_plugin")
        if ctx:
            # Use the local tool via context
            result = ctx.call_tool("hello_world", name="PocketFlow User")
            shared["final_answer"] = f"Result from tool: {result.get('message', '')}"
        else:
            shared["final_answer"] = "Hello from Programmatic Flow! (No PluginContext)"
        
        return "end"

def get_template_flow():
    start = HelloNode()
    flow = Flow(start=start)
    return flow
