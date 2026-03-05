from pocketcode.core.interfaces import Plugin
from pocketcode.plugins.core.agents.coder_agent import create_flow as _coder_flow
from pocketcode.plugins.core.agents.architect_agent import create_flow as _architect_flow
from pocketcode.plugins.core.agents.ask_agent import create_flow as _ask_flow


def get_plugin(config):
    return Plugin(
        name="core",
        version="0.1.1",
        description="Core built-in agents and tools",
        agents={
            "coder": _coder_flow(),
            "architect": _architect_flow(),
            "ask": _ask_flow(),
        },
        tools=[],
    )
