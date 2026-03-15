import asyncio
from pocketcode.core.agent_stack_vm import AgentStackVM
from pocketcode.core.stackvm_host import StackVmHostAdapter, StackVmHostContext

async def main():
    ctx = StackVmHostContext(
        agent_name="agents.survey",
        llm_router=None,
        tool_runtime=None,
        llm_profile="gemini_fast",
        system_prompt="",
        tool_definitions=[]
    )
    
    class MockAdapter(StackVmHostAdapter):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.prompts_num = 0

        async def prompt_text(self, question: str) -> str:
            self.prompts_num += 1
            if self.prompts_num == 1: return "Programming Languages"
            if self.prompts_num == 2: return "Answer 1"
            if self.prompts_num == 3: return "Answer 2"
            if self.prompts_num == 4: return "Answer 3"
            return ""
            
        async def llm_call(self, prompt: str) -> str:
            print(f"Mock LLM Prompt: {prompt}")
            return '["Question 1", "Question 2", "Question 3"]'

        def emit_effect(self, effect):
            kind = getattr(effect, "kind", "")
            if kind == "ask_user":
                pass
            return effect
            
        def execute_tool(self, tool_name, arguments):
            if tool_name == "core.create_directory": return {"success": True}
            if tool_name == "core.write_to_file": return {"success": True}
            return {"success": False}

    class DummyResult:
        effect = None
        
    store = {}
    adapter = MockAdapter(shared_store=store, host_context=ctx, result=DummyResult())
    vm = AgentStackVM(shared_store=store)
    vm.register_host_words(host_adapter=adapter)
    
    with open(".pocketcode/agent.survey/survey.agent.md") as f:
        src = f.read().split("```vm")[1].split("```")[0]
        
    print("Evaluating src...")
    await vm.eval(src)
    
    orig_ast = vm.execute_ast
    async def trace_ast(ast, *args, **kwargs):
        print(f"Exec AST len {len(ast)}: {ast[:5]}...")
        await orig_ast(ast, *args, **kwargs)

    vm.execute_ast = trace_ast

    print("Executing main...")
    await vm.execute_word("main")
    
    print("Loop starting...")
    for i in range(7):
        state = store.get("survey_state")
        if state is None or state == 0:
            val = await adapter.prompt_text("dummy")
            print(f"[{i}] Feeding {val!r}")
            store["initial_request"] = val
        else:
            val = await adapter.prompt_text("dummy")
            print(f"[{i}] Feeding {val!r}")
            store["initial_request"] = val
        await vm.execute_word("main")
        print(f"[{i}] Step done. State {store.get('survey_state')}")

asyncio.run(main())
