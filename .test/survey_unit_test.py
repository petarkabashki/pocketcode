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
            if self.prompts_num == 1: return "My Mock Survey"
            if self.prompts_num == 2: return "Question 1"
            if self.prompts_num == 3: return "Question 2"
            if self.prompts_num == 4: return ""
            if self.prompts_num == 5: return "Answer 1"
            if self.prompts_num == 6: return "Answer 2"
            return ""

        def emit_effect(self, effect):
            kind = getattr(effect, "kind", "")
            if kind == "ask_user":
                pass
            return effect
            
        def execute_tool(self, tool_name, arguments):
            if tool_name == "core.create_directory":
                import os
                try: os.makedirs(arguments.get("path", "."), exist_ok=True)
                except: pass
                return {"success": True}
            if tool_name == "core.write_to_file":
                with open(arguments.get("path", "out.txt"), "w") as f:
                    f.write(arguments.get("content", ""))
                return {"success": True}
            return {"success": False}

    class DummyResult:
        effect = None
    class DummyResult:
        effect = None
        
    store = {}
    adapter = MockAdapter(shared_store=store, host_context=ctx, result=DummyResult())
    vm = AgentStackVM(shared_store=store)
    vm.register_host_words(host_adapter=adapter)
    
    with open(".pocketcode/agent.survey/survey.agent.md") as f:
        src = f.read().split("```vm")[1]
    if "```" in src: src = src.split("```")[0]
        
    await vm.eval(src)
    
    # We must patch execute_word to catch ask-user because prompt_text has no connection
    # to the shared store. ask-user emits effect.
    orig_execute_word = vm.execute_word
    
    async def mock_execute(word):
        await orig_execute_word(word)
        if word == "main": print(vm.store)

    vm.execute_word = mock_execute
    
    # We provide interactive mock loop
    await vm.execute_word("main")
    
    for _ in range(7):
        state = store.get("survey_state")
        if state is None or state == 0:
            val = await adapter.prompt_text("dummy")
            print(f"Feeding {val!r}")
            store["initial_request"] = val
        else:
            val = await adapter.prompt_text("dummy")
            print(f"Feeding {val!r}")
            store["initial_request"] = val
        await vm.execute_word("main")
        print(f"Step done. State {store.get('survey_state')}")

asyncio.run(main())
