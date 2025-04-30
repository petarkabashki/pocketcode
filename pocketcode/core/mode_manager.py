# %% pocketcode/core/mode_manager.py
import logging
import importlib
import os  # Added
import pathlib # Added
from typing import Dict, Any, Optional

from pocketflow import Flow # Assuming Flow is importable

# Assuming these are the correct paths for your interfaces and components
from pocketcode.core.interfaces import BaseLlmClient
from pocketcode.core.llm_factory import create_llm_client
from pocketcode.core.memory_bank import MemoryBankManager # Assuming this exists

logger = logging.getLogger(__name__)

class ModeManager:
    """
    Manages the loading, configuration, and retrieval of PocketFlow-based modes.
    Centralizes LLM client initialization and dependency injection for flows.
    Dynamically discovers modes from the 'mode_flows' directory and validates against configuration.
    """
    def __init__(self,
                 global_config: Dict[str, Any],
                 tool_registry: Dict[str, str],
                 memory_manager: Optional[MemoryBankManager] = None):
        """
        Initializes the ModeManager.

        Args:
            global_config: The overall application configuration (settings).
            tool_registry: Dictionary mapping tool names to their implementation paths.
            memory_manager: An optional instance of MemoryBankManager.

        Raises:
            ValueError: If configuration/discovery mismatches are found (modes configured but not found, or vice-versa).
            FileNotFoundError: If the mode_flows directory doesn't exist.
        """
        self._global_config = global_config
        self._tool_registry = tool_registry
        self._memory_manager = memory_manager
        self._llm_clients: Dict[str, BaseLlmClient] = {} # Cache for LLM clients

        static_mode_configs = self._load_mode_configs()

        # Determine the mode flows directory path relative to this file
        # Assumes mode_manager.py is in pocketcode/core/
        flows_dir = pathlib.Path(__file__).parent.parent / "mode_flows"
        if not flows_dir.is_dir():
             # Raise error immediately if directory is missing
             raise FileNotFoundError(f"Mode flows directory not found at expected location: {flows_dir}")

        discovered_flow_creators = self._discover_mode_flows(flows_dir)

        # --- Validation and Merging ---
        final_mode_configs = {}
        configured_slugs = set(static_mode_configs.keys())
        discovered_slugs = set(discovered_flow_creators.keys())

        missing_configs = discovered_slugs - configured_slugs
        if missing_configs:
            raise ValueError(f"Discovered mode flows lack configuration in settings.yaml: {sorted(list(missing_configs))}")

        missing_flows = configured_slugs - discovered_slugs
        if missing_flows:
            raise ValueError(f"Configured modes lack corresponding flow files/functions in '{flows_dir.name}/': {sorted(list(missing_flows))}")

        # Process only modes that are both configured and discovered
        for mode_slug in configured_slugs.intersection(discovered_slugs):
            config = static_mode_configs[mode_slug]
            # Ensure config is a dictionary before adding the path
            if isinstance(config, dict):
                config['_flow_creator_path'] = discovered_flow_creators[mode_slug] # Add the path
                final_mode_configs[mode_slug] = config
                logger.debug(f"Validated and merged config for mode: {mode_slug}")
            else:
                 # This case should ideally be caught by config validation earlier
                 logger.error(f"Configuration for mode '{mode_slug}' is not a dictionary. Skipping.")
                 # Depending on strictness, could raise an error here too

        self._mode_configs = final_mode_configs # Store the validated configs

        logger.info("ModeManager initialized.")
        if not self._mode_configs:
             logger.warning("No valid modes were loaded after validation.")
        else:
             logger.info(f"Successfully loaded and validated modes: {sorted(list(self._mode_configs.keys()))}")


    def _load_mode_configs(self) -> Dict[str, Dict[str, Any]]:
        """Loads mode configurations from the global settings."""
        # Assuming modes are defined under a 'modes' key in global_config
        configs = self._global_config.get('modes', {})
        if not configs:
            logger.warning("No mode configurations found in global_config['modes'].")
        # TODO: Add more specific validation for mode configuration structure here if needed
        return configs

    def _discover_mode_flows(self, flows_dir_path: pathlib.Path) -> Dict[str, str]:
        """
        Dynamically discovers mode flow creator functions (create_<slug>_flow)
        in Python files within the specified directory.

        Args:
            flows_dir_path: The pathlib.Path object pointing to the mode flows directory.

        Returns:
            A dictionary mapping the mode slug (derived from filename) to the
            full import path of its creator function (e.g., 'asker': 'pocketcode.mode_flows.asker.create_asker_flow').
        """
        discovered_flows = {}
        logger.info(f"Discovering mode flows in: {flows_dir_path}")
        for filepath in flows_dir_path.glob("*.py"):
            if filepath.name == "__init__.py":
                continue

            mode_slug = filepath.stem # e.g., 'asker' from 'asker.py'
            expected_func_name = f"create_{mode_slug}_flow"
            # Construct module path relative to project structure (assuming pocketcode is importable)
            # e.g., pocketcode.mode_flows.asker
            # Relies on 'pocketcode' being in PYTHONPATH or installed
            module_name = f"pocketcode.mode_flows.{mode_slug}"

            try:
                module = importlib.import_module(module_name)
                if hasattr(module, expected_func_name):
                    creator_path = f"{module_name}.{expected_func_name}"
                    discovered_flows[mode_slug] = creator_path
                    logger.debug(f"Discovered flow creator for '{mode_slug}': {creator_path}")
                else:
                    # Log clearly if the function is missing, as this will cause validation failure later
                    logger.warning(f"Module '{module_name}' loaded, but missing expected function '{expected_func_name}'. This mode will fail validation.")
            except ImportError as e:
                # Log clearly, as this will cause validation failure later
                logger.error(f"Failed to import mode flow module '{module_name}'. This mode will fail validation. Error: {e}", exc_info=False) # Less verbose log
            except Exception as e:
                 logger.error(f"Unexpected error discovering flow for '{mode_slug}': {e}", exc_info=True)

        logger.info(f"Discovery scan complete. Found potential flow creators for: {sorted(list(discovered_flows.keys()))}")
        return discovered_flows

    def _get_llm_client(self, mode_name: str) -> Optional[BaseLlmClient]:
        """
        Gets or initializes the LLM client for a given mode based on its config.
        Uses caching to avoid re-initializing clients.
        (No changes needed from original)
        """
        mode_config = self._mode_configs.get(mode_name)
        if not mode_config:
            # This log might be redundant now due to __init__ validation, but safe to keep
            logger.error(f"Attempted to get LLM client for non-validated/missing mode '{mode_name}'.")
            return None

        llm_config = mode_config.get('llm_config')
        if not llm_config:
            logger.warning(f"Mode '{mode_name}' has no 'llm_config'. Cannot create LLM client.")
            return None

        # Create a unique key for caching based on LLM config details
        cache_key = f"{llm_config.get('provider')}_{llm_config.get('model')}"

        if cache_key not in self._llm_clients:
            logger.info(f"LLM client for '{cache_key}' not found in cache. Initializing...")
            try:
                providers_config = self._global_config.get('providers', {})
                client = create_llm_client(llm_config, providers_config)
                if client:
                    self._llm_clients[cache_key] = client
                    logger.info(f"Successfully initialized and cached LLM client for '{cache_key}'.")
                else:
                    logger.error(f"LlmClientFactory failed to create client for mode '{mode_name}' with config: {llm_config}")
                    return None # Explicitly return None on failure
            except Exception as e:
                logger.error(f"Failed to initialize LLM client for mode '{mode_name}': {e}", exc_info=True)
                return None # Return None on exception
        else:
             logger.debug(f"Using cached LLM client for '{cache_key}'.")


        return self._llm_clients.get(cache_key) # Use .get for safety

    def get_available_modes(self) -> Dict[str, Dict[str, Any]]:
        """Returns the validated and loaded mode configurations."""
        return self._mode_configs.copy() # Return a copy

    # Helper to get the prepared shared store if needed separately
    def prepare_initial_store(self, mode_name: str, initial_context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
         """Prepares the initial shared store with dependencies for a given mode."""
         mode_config = self._mode_configs.get(mode_name)
         if not mode_config:
             logger.error(f"Mode '{mode_name}' not found in validated configurations.")
             return None

         llm_client = self._get_llm_client(mode_name)
         # Check if LLM is required and failed to initialize
         if not llm_client and mode_config.get('requires_llm', True):
              logger.error(f"Failed to get required LLM client for mode '{mode_name}'. Cannot prepare store.")
              return None

         shared_store = initial_context if initial_context else {}
         shared_store.update({
             "mode_name": mode_name,
             "mode_config": mode_config,
             "global_config": self._global_config, # Inject global config
             "tool_registry": self._tool_registry, # Inject tool registry
             "llm_client": llm_client, # Inject the specific client instance or None
             "memory_manager": self._memory_manager, # Inject memory manager
             # Add any other common context needed by flows/nodes
             "results": {}, # Standard place for results
         })
         logger.debug(f"Prepared initial shared store for mode '{mode_name}' with keys: {list(shared_store.keys())}")
         return shared_store

    # Refined get_flow to just return the flow structure
    def get_flow_structure(self, mode_name: str) -> Optional[Flow]:
         """
         Gets the basic flow structure for a mode using the dynamically discovered creator function path
         stored in its configuration.
         """
         logger.info(f"Requesting flow structure for mode: '{mode_name}'")
         mode_config = self._mode_configs.get(mode_name)
         if not mode_config:
             logger.error(f"Mode '{mode_name}' not found in validated configuration.")
             return None

         # Use the dynamically discovered path stored during __init__
         flow_creator_path = mode_config.get('_flow_creator_path')
         if not flow_creator_path:
             # This should not happen if __init__ validation passed, but check defensively
             logger.error(f"Internal Error: Mode '{mode_name}' configuration missing '_flow_creator_path'. Cannot load flow.")
             return None

         logger.debug(f"Attempting to load flow structure using creator path: {flow_creator_path}")
         try:
             module_path, func_name = flow_creator_path.rsplit('.', 1)
             module = importlib.import_module(module_path)
             create_flow_func = getattr(module, func_name)

             # Assume create_flow function now takes no arguments
             flow = create_flow_func()

             if not isinstance(flow, Flow):
                  logger.error(f"Flow creation function '{func_name}' from '{flow_creator_path}' did not return a PocketFlow Flow instance.")
                  return None

             logger.info(f"Successfully retrieved flow structure for mode '{mode_name}' using '{flow_creator_path}'.")
             return flow

         except (ImportError, AttributeError, ValueError, TypeError) as e:
             logger.error(f"Failed to load or create flow structure from {flow_creator_path} for mode '{mode_name}': {e}", exc_info=True)
             return None
         except Exception as e:
             logger.error(f"Unexpected error getting flow structure for mode '{mode_name}' using {flow_creator_path}: {e}", exc_info=True)
             return None