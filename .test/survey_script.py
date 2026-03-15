import asyncio
from pocketcode.core.agent_stack_vm import AgentStackVM
from pocketcode.core.stackvm_host import LocalStackVmHostAdapter, ExecutionContext

async def main():
    ctx = ExecutionContext(
        flow_path="agents.survey",
        workspace_root=".",
        agent_name="agents.survey",
        system_prompt="",
        llm_profile="gemini_fast"
    )
    
    class MockAdapter(LocalStackVmHostAdapter):
        def __init__(self, context):
            super().__init__(context)
            self.prompts_num = 0

        async def prompt_text(self, question: str) -> str:
            print(f"Prompt output: {question}")
            self.prompts_num += 1
            if self.prompts_num == 1:
                return "My Mock Survey"
            elif self.prompts_num == 2:
                return "Mock Question 1"
            elif self.prompts_num == 3:
                return "Mock Question 2"
            elif self.prompts_num == 4:
                return ""
            elif self.prompts_num == 5:
                return "Mock Answer 1"
            elif self.prompts_num == 6:
                return "Mock Answer 2"
            return ""

        def execute_tool(self, tool_name: str, arguments: dict) -> dict:
            print(f"Executing tool: {tool_name} with args {arguments}")
            return {"status": "success"}

    adapter = MockAdapter(ctx)
    vm = AgentStackVM(adapter, ctx)
    
    with open(".pocketcode/agent.survey/survey.agent.md") as f:
        src = f.read().split("```vm")[1]
        
    if "```" in src:
        src = src.split("```")[0]
        
    await vm.load_source(src)
    
    # Run the state machine
    await vm.execute_word("main")
    print(f"First step. Store: {vm.store}")
    
    mock_inputs = ["My Mock Survey", "Mock Question 1", "Mock Question 2", "", "Mock Answer 1", "Mock Answer 2"]
    
    for i in mock_inputs:
        vm.store["req"] = i
        await vm.execute_word("main")
        print(f"Executed with {i}. State: {vm.store.get('survey_state')}")

asyncio.run(main())
