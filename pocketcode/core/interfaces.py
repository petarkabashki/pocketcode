#%% pocketcode/core/interfaces.py
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict

# Import the factory function (will be updated later to return BaseLlmClient)
# from pocketcode.core.llm_factory import create_llm_client # Commented out temporarily

# Guard against circular imports if pocketflow is imported here
# from pocketflow import Flow, AsyncFlow 

logger = logging.getLogger(__name__)

# --- LLM Client Interface ---
class BaseLlmClient(ABC):
    """Abstract base class for LLM client wrappers."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generates text based on the prompt and parameters.

        Args:
            prompt: The input prompt string.
            **kwargs: Provider-specific parameters (e.g., temperature, max_tokens, model).
                      The wrapper implementation is responsible for handling these.

        Returns:
            The generated text response as a string.

        Raises:
            NotImplementedError: If the method is not implemented by a subclass.
            Exception: Provider-specific exceptions during the API call.
        """
        pass

# --- BaseTool remains unchanged ---
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

    @property
    def execution_mode(self) -> str:
        """Execution strategy for the tool. Defaults to in-process execution."""
        return "inline"

    @property
    def timeout_seconds(self) -> float | None:
        """Optional timeout for managed subprocess execution."""
        return None

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Execute the tool's functionality."""
        pass

    def spawn_subprocess(self, **kwargs) -> Any:
        """Optional hook for tools that support managed subprocess execution."""
        raise NotImplementedError(f"Tool '{self.name}' does not implement managed subprocess execution.")

    def handle_subprocess_result(self, *, returncode: int, stdout: str, stderr: str, **kwargs) -> Any:
        """Optional hook to turn subprocess output into the tool result payload."""
        raise NotImplementedError(f"Tool '{self.name}' does not implement managed subprocess result handling.")

# BaseWorkflow might be more conceptual or directly use PocketFlow types
# class BaseWorkflow(ABC): ...
