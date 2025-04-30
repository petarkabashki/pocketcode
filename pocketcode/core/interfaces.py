#%% pocketcode/core/interfaces.py
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

# Import the factory function (will be updated later to return BaseLlmClient)
# from pocketcode.core.llm_factory import create_llm_client # Commented out temporarily

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

# --- Mode Interface ---
class BaseMode(ABC):
    """
    Abstract base class for all agentic modes.
    Handles common initialization, including LLM client creation.
    """
    def __init__(self,
                 config: Dict[str, Any],
                 global_config: Dict[str, Any],
                 tool_registry: Dict[str, str],
                 memory_manager: Optional[Any] = None): # Added memory_manager for consistency
        """
        Initializes the BaseMode, including the LLM client wrapper.

        Args:
            config: The configuration dictionary for this specific mode.
            global_config: The overall application configuration (settings).
            tool_registry: Dictionary mapping tool names to their implementation paths.
            memory_manager: An optional instance of MemoryBankManager or similar.
        """
        self._config = config
        self._global_config = global_config
        self._tool_registry = tool_registry
        self._memory_manager = memory_manager # Store memory manager if provided
        self._llm_client: Optional[BaseLlmClient] = None # Changed type hint

        logger.debug(f"Initializing BaseMode for mode defined by config: {config.get('slug', 'N/A')}")

        # --- LLM Client Initialization ---
        # Import factory function here to avoid circular dependency at module level
        from pocketcode.core.llm_factory import create_llm_client

        try:
            # Merge default and mode-specific LLM configs
            default_llm_config = global_config.get('defaults', {}).get('llm_config', {})
            mode_llm_config = config.get('llm_config', {})
            final_llm_config = default_llm_config.copy()
            final_llm_config.update(mode_llm_config) # Mode config overrides defaults

            # Get provider API keys config
            providers_config = global_config.get('providers', {})

            if not final_llm_config.get('provider'):
                 logger.warning(f"No LLM provider specified in defaults or mode config for {self.name}. LLM client will not be created.")
            elif not providers_config:
                 logger.warning("No 'providers' section found in global config. Cannot retrieve API keys for LLM client.")
            else:
                logger.info(f"Attempting to create LLM client for mode '{self.name}' using config: {final_llm_config}")
                # create_llm_client should now return an instance of BaseLlmClient
                self._llm_client = create_llm_client(final_llm_config, providers_config)

                if self._llm_client:
                    logger.info(f"LLM client wrapper successfully created for mode '{self.name}'.")
                else:
                    # Error logged within create_llm_client
                    logger.error(f"Failed to create LLM client wrapper for mode '{self.name}'. Mode may not function correctly if LLM is required.")

        except Exception as e:
            logger.exception(f"Unexpected error during LLM client initialization for mode '{self.name}': {e}")
            self._llm_client = None # Ensure client is None on error

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name (slug) of the mode."""
        # Implementation expected in subclasses, often derived from self._config
        return self._config.get('slug', 'unknown_mode')

    @property
    def display_name(self) -> str:
        """User-friendly display name."""
        # Default implementation, subclasses can override
        return self._config.get('name', self.name.replace('_', ' ').title())

    @property
    def description(self) -> str:
        """Description of the mode's purpose."""
        # Default implementation, subclasses can override
        return self._config.get('description', 'No description provided.')

    @property
    def llm_client(self) -> Optional[BaseLlmClient]: # Changed type hint
        """Provides access to the initialized LLM client wrapper."""
        return self._llm_client

    @abstractmethod
    def process_request(self, request: Any, context: Dict) -> Any:
        """Process an incoming request within the mode's context."""
        pass

    # Add other common methods/properties as needed

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

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Execute the tool's functionality."""
        pass

# BaseWorkflow might be more conceptual or directly use PocketFlow types
# class BaseWorkflow(ABC): ...