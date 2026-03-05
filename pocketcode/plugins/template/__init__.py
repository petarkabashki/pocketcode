from pocketcode.core.interfaces import Plugin
from .agent import get_template_flow
from .tools.hello import HelloTool

def get_plugin(config):
    return Plugin(
        name="template",
        version="0.1.0",
        agents={
            "template-agent": get_template_flow()
        },
        tools=[HelloTool()]
    )
