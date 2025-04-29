# pocketcode/core/interfaces.py
from abc import ABC, abstractmethod
from typing import Any, Dict, List

class BaseMode(ABC):
    """Abstract base class for all agentic modes."""
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the mode."""
        pass

    @abstractmethod
    def process_request(self, request: Any, context: Dict) -> Any:
        """Process an incoming request within the mode's context."""
        pass

    # Add other common methods/properties as needed (e.g., description)

class BaseTool(ABC):
    """Abstract base class for all tools."""
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what the tool does."""
        pass

    @property
    @abstractmethod
    def schema(self) -> Dict:
        """Input schema for the tool (e.g., JSON schema)."""
        pass

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Execute the tool's functionality."""
        pass

# BaseWorkflow might be more conceptual or directly use PocketFlow types
# class BaseWorkflow(ABC): ...