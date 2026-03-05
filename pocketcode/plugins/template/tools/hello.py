from __future__ import annotations

import logging
from typing import Any, Dict

from pocketcode.core.interfaces import BaseTool

logger = logging.getLogger(__name__)

class HelloTool(BaseTool):
    @property
    def name(self) -> str:
        return "hello_world"

    @property
    def description(self) -> str:
        return "A sample tool that prints a greeting"

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The name of the person to greet.", "default": "World"},
            },
        }

    def execute(self, **kwargs) -> Any:
        name = kwargs.get("name", "World")
        greeting = f"Hello, {name}!"
        print(greeting)
        return {"success": True, "message": greeting}
