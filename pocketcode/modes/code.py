#%% pocketcode/modes/code.py
import logging
import inspect # Keep inspect for potential future use, but not for flow args check
from typing import Dict, Any, Optional
from pocketcode.core.interfaces import BaseMode
from pocketcode.core.memory_bank import MemoryBankManager

# Assuming pocketflow is installed and Flow is importable
# from pocketflow import Flow # Placeholder
# from pocketcode.flows.code import create_code_flow # Placeholder

logger = logging.getLogger(__name__)

# %% Helper function to format CLI context (Unchanged)
def _format_cli_context(cli_context_data: Dict[str, Any]) -> Optional[str]:
    """Formats the CLI context dictionary into a string for LLM prompts."""
    if not cli_context_data or not any(cli_context_data.values()):
        return None # Return None if context is empty

    lines = ["--- CLI Context ---"]
    if cli_context_data.get("files"):
        lines.append("Files:")
        for item in sorted(list(cli_context_data["files"])): lines.append(f"- {item}")
    if cli_context_data.get("folders"):
        lines.append("Folders:")
        for item in sorted(list(cli_context_data["folders"])): lines.append(f"- {item}")
    if cli_context_data.get("urls"):
        lines.append("URLs:")
        for item in sorted(list(cli_context_data["urls"])): lines.append(f"- {item}")
    if cli_context_data.get("snippets"):
        lines.append("Snippets:")
        for name, content in sorted(cli_context_data["snippets"].items()):
            lines.append(f"- {name}: {content}")
    lines.append("-------------------")
    return "\n".join(lines)


class CodeMode(BaseMode):
    """
    Mode specialized for writing and modifying code using a PocketFlow.
    Loads configuration and orchestrates the code-specific PocketFlow.
    Can utilize a MemoryBankManager for context.
    """
    # %% Modified __init__ signature
    def __init__(self,
                 config: Dict[str, Any],
                 global_config: Dict[str, Any],
                 tool_registry: Dict[str, str],
                 memory_manager: Optional[MemoryBankManager] = None):
        """
        Initializes the CodeMode with its specific configuration, global settings,
        tool registry, and optional memory manager.

        Args:
            config: The configuration dictionary for this mode from settings.yaml.
            global_config: The overall application configuration (settings).
            tool_registry: Dictionary mapping tool names to their implementation paths.
            memory_manager: An optional instance of MemoryBankManager.
        """
        self._config = config
        self._global_config = global_config # Store global config
        self._tool_registry = tool_registry # Store tool registry
        self._memory_manager = memory_manager # Store the memory manager
        self._flow = None # Flow will be created lazily or on demand
        logger.info(f"CodeMode initialized with config: {config.get('name', 'N/A')}")
        if self._memory_manager:
            logger.info("MemoryBankManager instance provided to CodeMode.")
        # Potentially load prompt templates, custom instructions here

    @property
    def name(self) -> str:
        """Returns the unique name (slug) of the mode."""
        # Assuming the key used to fetch this config is the name/slug.
        # Let's refine this - the config passed should ideally contain its own key/slug
        # For now, rely on the config dict passed during instantiation.
        return self._config.get('slug', 'code') # Default to 'code' if slug isn't injected

    @property
    def display_name(self) -> str:
        """Returns the user-friendly display name."""
        return self._config.get('name', 'Code Mode')

    @property
    def description(self) -> str:
        """Returns the mode's description."""
        return self._config.get('description', 'Handles coding tasks.')

    # %% Modified _get_flow method
    def _get_flow(self):
        """Lazily loads and creates the PocketFlow instance."""
        if self._flow is None:
            flow_module_path = self._config.get('flow_module')
            if not flow_module_path:
                logger.error("Missing 'flow_module' in CodeMode configuration.")
                raise ValueError("CodeMode configuration lacks 'flow_module'.")

            try:
                # Dynamically import the flow creation function
                module_path, func_name = flow_module_path.rsplit('.', 1)
                module = __import__(module_path, fromlist=[func_name])
                create_flow_func = getattr(module, func_name)

                # %% Prepare arguments for the flow creator using correct names
                flow_args = {
                    "mode_config": self._config,
                    "global_config": self._global_config,
                    "tool_registry": self._tool_registry
                    # memory_manager is not passed here as create_code_flow doesn't expect it
                }

                # %% Create the flow instance
                # Removed the inspect logic and conditional memory_manager passing
                self._flow = create_flow_func(**flow_args)

                logger.info(f"PocketFlow created for CodeMode using {flow_module_path}")
            except (ImportError, AttributeError, ValueError, TypeError) as e:
                logger.error(f"Failed to load or create flow from {flow_module_path}: {e}", exc_info=True) # Log traceback
                raise RuntimeError(f"Could not initialize CodeMode flow: {e}") from e
        return self._flow

    # %% process_request method (Unchanged logic, but relies on fixed _get_flow)
    def process_request(self, request: Any, context: Dict) -> Any:
        """
        Processes an incoming request using the mode's configured PocketFlow.

        Args:
            request: The user's request payload.
            context: Additional context (e.g., session info, history, cli_context).

        Returns:
            The result produced by the PocketFlow execution.
        """
        logger.info(f"CodeMode processing request: {request}")
        logger.debug(f"CodeMode received context keys: {list(context.keys())}") # Log received context keys

        # %% Format CLI context if present (Unchanged)
        formatted_cli_context = None
        cli_context_data = context.get('cli_context')
        if cli_context_data:
            logger.debug(f"CLI context received: {cli_context_data}")
            formatted_cli_context = _format_cli_context(cli_context_data)
            if formatted_cli_context:
                logger.info("Formatted CLI context will be passed to the flow.")
            else:
                 logger.info("CLI context received but was empty.")
        else:
             logger.info("No CLI context found in the received context dictionary.")


        # %% Memory bank access (Unchanged)
        if self._memory_manager:
            try:
                pass # Placeholder for actual usage
            except Exception as e:
                logger.error(f"Failed to load memory bank content in CodeMode: {e}")

        # %% Get the flow (Now uses the fixed _get_flow)
        flow = self._get_flow()

        # %% Initialize the shared store for the flow run (Unchanged)
        shared_store = {
            "initial_request": request,
            "context": context, # Pass original context
            "mode_config": self._config, # Make mode config available to nodes
            "formatted_cli_context": formatted_cli_context,
            "results": {} # Placeholder for flow outputs
        }

        # %% Flow execution (Placeholder logic unchanged)
        try:
            logger.warning("PocketFlow execution (`flow.run()`) is currently a placeholder.")
            cli_info = "\n(CLI context was provided)" if formatted_cli_context else ""
            final_result = f"CodeMode processed request '{request}' using flow.{cli_info} Final state (placeholder): {shared_store.get('results')}"
            shared_store["results"]["final_output"] = final_result # Simulate flow output

            logger.info("CodeMode PocketFlow execution completed (placeholder).")
            return shared_store.get("results", {}).get("final_output", "Processing complete (placeholder).")
        except Exception as e:
            logger.error(f"Error during CodeMode PocketFlow execution: {e}", exc_info=True)
            return f"An error occurred during processing: {e}"

# Example instantiation comments (Unchanged)
# config_loader = ...
# settings = config_loader.load_settings()
# registered = register_components(settings)
# CodeModeClass = registered['modes'].get('code')
# if CodeModeClass:
#     # Now requires global_config and tool_registry
#     # code_mode_instance = CodeModeClass(
#     #     config=settings['modes']['code'],
#     #     global_config=settings,
#     #     tool_registry=registered['tools']
#     # )