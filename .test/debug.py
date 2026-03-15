import sys
print("A", flush=True)
import asyncio
print("B", flush=True)
from pocketcode.core.agent_stack_vm import AgentStackVM
print("C", flush=True)

async def main():
    print("D", flush=True)
    vm = AgentStackVM()
    print("E", flush=True)
    with open(".pocketcode/agent.survey/survey.agent.md") as f:
        src = f.read().split("```vm")[1].split("```")[0]
    print("F", flush=True)
    await vm.eval(src)
    print("G", flush=True)

print("Starting main loop", flush=True)
asyncio.run(main())
print("Finished", flush=True)
