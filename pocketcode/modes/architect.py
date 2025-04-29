# pocketcode/modes/architect.py
import logging
from typing import Dict, Any, Optional # Added Optional
from pocketcode.core.interfaces import BaseMode
from pocketcode.core.memory_bank import MemoryBankManager # Added import

# Assuming pocketflow is installed and Flow is importable
# from pocketflow import Flow # Placeholder
# from pocketcode.flows.architect import create_architect_flow # Placeholder

logger = logging.getLogger(__name__)

class ArchitectMode(BaseMode):
    """
    Mode for planning, designing system architecture, and documentation using PocketFlow.
    Loads configuration and orchestrates the architect-specific PocketFlow.
    Can utilize a MemoryBankManager for context.
    """
    # Modified __init__ signature
    def __init__(self, config: Dict[str, Any], memory_manager: Optional[MemoryBankManager] = None):
        """
        Initializes the ArchitectMode with its specific configuration and optional memory manager.

        Args:
            config: The configuration dictionary for this mode from settings.yaml.
            memory_manager: An optional instance of MemoryBankManager.
        """
        self._config = config
        self._memory_manager = memory_manager # Store the memory manager
        self._flow = None # Flow will be created lazily or on demand
        logger.info(f"ArchitectMode initialized with config: {config.get('name', 'N/A')}")
        if self._memory_manager:
            logger.info("MemoryBankManager instance provided to ArchitectMode.")
        # Potentially load prompt templates, custom instructions here

    @property
    def name(self) -> str:
        """Returns the unique name (slug) of the mode."""
        # Assuming the key used to fetch this config is the name/slug.
        return self._config.get('slug', 'architect') # Default if slug isn't injected

    @property
    def display_name(self) -> str:
        """Returns the user-friendly display name."""
        return self._config.get('name', 'Architect Mode')

    @property
    def description(self) -> str:
        """Returns the mode's description."""
        return self._config.get('description', 'Handles architecture and documentation tasks.')

    def _get_flow(self):
        """Lazily loads and creates the PocketFlow instance."""
        if self._flow is None:
            flow_module_path = self._config.get('flow_module')
            if not flow_module_path:
                logger.error("Missing 'flow_module' in ArchitectMode configuration.")
                raise ValueError("ArchitectMode configuration lacks 'flow_module'.")

            try:
                # Dynamically import the flow creation function
                module_path, func_name = flow_module_path.rsplit('.', 1)
                module = __import__(module_path, fromlist=[func_name])
                create_flow_func = getattr(module, func_name)

                # Prepare arguments for the flow creator
                flow_args = {
                    "config": self._config,
                    "memory_manager": self._memory_manager # Pass manager to flow creator
                }

                # Check if the creator function accepts memory_manager before passing
                import inspect
                sig = inspect.signature(create_flow_func)
                if "memory_manager" in sig.parameters:
                     self._flow = create_flow_func(**flow_args)
                else:
                     logger.warning(f"Flow creator {flow_module_path} does not accept 'memory_manager'. Creating flow without it.")
                     del flow_args["memory_manager"] # Remove if not accepted
                     self._flow = create_flow_func(**flow_args)

                logger.info(f"PocketFlow created for ArchitectMode using {flow_module_path}")
            except (ImportError, AttributeError, ValueError, TypeError) as e: # Added TypeError
                logger.error(f"Failed to load or create flow from {flow_module_path}: {e}")
                raise RuntimeError(f"Could not initialize ArchitectMode flow: {e}") from e
        return self._flow

    def process_request(self, request: Any, context: Dict) -> Any:
        """
        Processes an incoming request using the mode's configured PocketFlow.

        Args:
            request: The user's request payload.
            context: Additional context (e.g., session info, history).

        Returns:
            The result produced by the PocketFlow execution.
        """
        logger.info(f"ArchitectMode processing request: {request}")

        # Example: Access memory bank content if needed before calling flow
        if self._memory_manager:
            try:
                # Example: Load specific file content
                # product_context = self._memory_manager.get_file_content("productContext.md")
                # if product_context:
                #     logger.debug("Product context loaded from memory bank.")
                #     context['product_context'] = product_context # Pass to flow via context
                pass # Placeholder for actual usage
            except Exception as e:
                logger.error(f"Failed to load memory bank content in ArchitectMode: {e}")

        flow = self._get_flow()

        # Initialize the shared store for the flow run
        shared_store = {
            "initial_request": request,
            "context": context,
            "mode_config": self._config, # Make mode config available to nodes
            # "memory_manager": self._memory_manager, # Optionally pass manager directly to flow store
            "results": {} # Placeholder for flow outputs
        }

        try:
            # Assuming a synchronous flow for now. Adapt if async needed.
            # flow.run(shared_store) # Replace with actual PocketFlow run method
            logger.warning("PocketFlow execution (`flow.run()`) is currently a placeholder.")
            # Placeholder result
            final_result = f"ArchitectMode processed request '{request}' using flow. Final state (placeholder): {shared_store.get('results')}"
            shared_store["results"]["final_output"] = final_result # Simulate flow output

            logger.info("ArchitectMode PocketFlow execution completed (placeholder).")
            return shared_store.get("results", {}).get("final_output", "Processing complete (placeholder).")
        except Exception as e:
            logger.error(f"Error during ArchitectMode PocketFlow execution: {e}", exc_info=True)
            # Depending on requirements, might return error details or a generic message
            return f"An error occurred during processing: {e}"