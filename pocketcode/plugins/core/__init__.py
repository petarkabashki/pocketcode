from pocketcode.core.interfaces import Plugin
# Placeholder: for now we don't have single_agent.py ready, but let's assume it exists
# from .workflows.single_agent import get_single_agent_flow

def get_plugin(config):
    return Plugin(
        name="core",
        version="0.1.1",
        agents={}, # Add agents here once single_agent.py is implemented
        tools=[]
    )
