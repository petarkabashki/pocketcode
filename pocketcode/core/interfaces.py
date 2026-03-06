#%% pocketcode/core/interfaces.py
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

# Import the factory function (will be updated later to return BaseLlmClient)
# from pocketcode.core.llm_factory import create_llm_client # Commented out temporarily

# Guard against circular imports if pocketflow is imported here
# from pocketflow import Flow, AsyncFlow 

logger = logging.getLogger(__name__)

@dataclass
class Plugin:
    """Standard container for plugin resources."""
    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    tools: List[Callable] = field(default_factory=list)
    prompts: Dict[str, str] = field(default_factory=dict)
    agents: Dict[str, Any] = field(default_factory=dict) # Union[Flow, AsyncFlow]
    metadata: Dict[str, Any] = field(default_factory=dict)

class PluginContext:
    """Passed to each Flow in shared['_plugin']."""
    def __init__(self, plugin: Plugin, runtime: Any):
        self.name = plugin.name
        self.tools = {}
        for t in plugin.tools:
            # Handle both functions (has __name__) and classes/instances with .name
            name = getattr(t, "__name__", getattr(t, "name", str(t)))
            self.tools[name] = t
        self.prompts = plugin.prompts
        self._runtime = runtime

    def get_prompt(self, name: str) -> str:
        """Retrieve a local prompt by name."""
        if name in self.prompts:
            return self.prompts[name]
        
        # Fallback: try to resolve via runtime/filesystem if not pre-loaded
        try:
            from pocketcode.core.prompt_loader import resolve_prompt_bundle
            from pathlib import Path
            
            # Use self.name as the plugin key
            plugin_root_str = getattr(self._runtime, "_plugins", {}).plugin_roots.get(self.name)
            if not plugin_root_str:
                 return ""
                 
            plugin_root = Path(plugin_root_str)
            prompt, _ = resolve_prompt_bundle(
                {}, 
                base_dir=plugin_root,
                default_files=[f"prompts/{name}.md", f"prompts/{name}.txt"]
            )
            return prompt
        except Exception:
            return ""

    def call_tool(self, tool_name: str, **kwargs) -> Any:
        """Call a plugin-local tool."""
        if tool_name in self.tools:
            tool = self.tools[tool_name]
            if hasattr(tool, "execute"):
                return tool.execute(**kwargs)
            return tool(**kwargs)
        # Fallback to runtime tool execution if not local
        return self._runtime.execute_tool(tool_name, **kwargs)

def get_plugin_context(shared: Dict[str, Any]) -> Optional[PluginContext]:
    """Helper to retrieve PluginContext from pocketflow shared store."""
    return shared.get("_plugin")

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
            llm_section = global_config.get("llm", {}) if isinstance(global_config, dict) else {}
            llm_profiles = llm_section.get("profiles", {}) if isinstance(llm_section, dict) else {}
            default_profile = llm_section.get("default_profile") if isinstance(llm_section, dict) else None
            default_llm_config = (
                llm_profiles.get(default_profile, {})
                if isinstance(llm_profiles, dict) and default_profile in llm_profiles
                else {}
            )
            mode_llm_config = config.get('llm_config', {})
            final_llm_config = default_llm_config.copy()
            final_llm_config.update(mode_llm_config) # Mode config overrides defaults

            # Get provider API keys config
            providers_config = llm_section.get('providers', {}) if isinstance(llm_section, dict) else {}

            if not final_llm_config.get('provider'):
                 logger.warning(f"No LLM provider specified in defaults or mode config for {self.name}. LLM client will not be created.")
            elif not providers_config:
                 logger.warning("No 'llm.providers' section found in global config. Cannot retrieve API keys for LLM client.")
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
