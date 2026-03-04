# %% pocketcode/core/mode_manager.py
import logging
import importlib
import os
import pathlib
from typing import Dict, Any, Optional

from pocketflow import Flow # Assuming Flow is importable

# Assuming these are the correct paths for your interfaces and components
from pocketcode.core.interfaces import BaseLlmClient
from pocketcode.core.llm_factory import create_llm_client
from pocketcode.core.context_elephant_store import ContextElephantStoreManager # Assuming this exists

logger = logging.getLogger(__name__)

class ModeManager:
    """
    Manages the loading, configuration, and retrieval of PocketFlow-based modes.
    Centralizes LLM client initialization and dependency injection for flows.
    Dynamically discovers modes from the 'mode_flows' directory and validates against configuration.
    Caches the active mode's flow instance for reuse.
    """
    def __init__(self,
                 global_config: Dict[str, Any],
                 tool_registry: Dict[str, Any],
                 memory_manager: Optional[ContextElephantStoreManager] = None):
        """
        Initializes the ModeManager.

        Args:
            global_config: The overall application configuration (settings).
            tool_registry: Dictionary mapping tool names to registered tool classes.
            memory_manager: An optional instance of ContextElephantStoreManager.

        Raises:
            ValueError: If configuration/discovery mismatches are found (modes configured but not found).
            FileNotFoundError: If the mode_flows directory doesn't exist.
        """
        self._global_config = global_config
        self._tool_registry = tool_registry
        self._memory_manager = memory_manager
        self._llm_clients: Dict[str, BaseLlmClient] = {} # Cache for LLM clients

        # Cache flow instances by mode slug.
        self._flow_cache: Dict[str, Flow] = {}

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
            # Modified to log a warning instead of raising an error
            logger.warning(
                "Discovered mode flows lack configuration and will be ignored: %s",
                sorted(list(missing_configs)),
            )
            # Do NOT raise ValueError here

        missing_flows = configured_slugs - discovered_slugs
        if missing_flows:
            # Keep this check as configured modes must have a corresponding flow
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
        """
        mode_config = self._mode_configs.get(mode_name)
        if not mode_config:
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
                llm_section = self._global_config.get("llm", {}) if isinstance(self._global_config, dict) else {}
                providers_config = llm_section.get('providers', {}) if isinstance(llm_section, dict) else {}
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

         cli_context = shared_store.get("cli_context", {})
         shared_store["formatted_cli_context"] = self._format_cli_context(cli_context)

         context_content = {}
         if self._memory_manager:
             try:
                 context_content = self._memory_manager.load_content()
             except Exception as e:
                 logger.error(f"Failed loading context elephant store content: {e}", exc_info=True)
         shared_store["context_memory_store_content"] = context_content if context_content else "N/A"
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

    def _format_cli_context(self, cli_context_data: Dict[str, Any]) -> str:
         if not cli_context_data or not any(cli_context_data.values()):
             return "None provided."

         lines = []
         if cli_context_data.get("files"):
             lines.append("Files:")
             lines.extend(f"- {item}" for item in sorted(list(cli_context_data["files"])))
         if cli_context_data.get("folders"):
             lines.append("Folders:")
             lines.extend(f"- {item}" for item in sorted(list(cli_context_data["folders"])))
         if cli_context_data.get("urls"):
             lines.append("URLs:")
             lines.extend(f"- {item}" for item in sorted(list(cli_context_data["urls"])))
         if cli_context_data.get("snippets"):
             lines.append("Snippets:")
             for name, content in sorted(cli_context_data["snippets"].items()):
                 lines.append(f"- {name}: {content}")
         return "\n".join(lines) if lines else "None provided."

    def get_or_create_flow(self, mode_name: str) -> Optional[Flow]:
        """
        Gets a cached flow instance for the mode, or creates and caches it.
        """
        logger.info(f"Requesting flow for mode: '{mode_name}'")

        if mode_name in self._flow_cache:
            logger.debug(f"Returning cached flow instance for mode: '{mode_name}'")
            return self._flow_cache[mode_name]

        logger.info(f"No cached flow for '{mode_name}'. Creating new flow instance.")

        mode_config = self._mode_configs.get(mode_name)
        if not mode_config:
            logger.error(f"Mode '{mode_name}' not found in validated configuration. Cannot create flow.")
            return None

        flow_creator_path = mode_config.get('_flow_creator_path')
        if not flow_creator_path:
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

            logger.info(f"Successfully created and cached flow instance for mode '{mode_name}'.")
            self._flow_cache[mode_name] = flow
            return flow

        except (ImportError, AttributeError, ValueError, TypeError) as e:
            logger.error(f"Failed to load or create flow from {flow_creator_path} for mode '{mode_name}': {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting flow for mode '{mode_name}' using {flow_creator_path}: {e}", exc_info=True)
            return None

    # Keep get_flow_structure for potential external use if needed, but internal logic should use get_or_create_flow
    def get_flow_structure(self, mode_name: str) -> Optional[Flow]:
         """
         Gets the basic flow structure for a mode using the dynamically discovered creator function path
         stored in its configuration. This method does NOT cache the flow instance.
         Internal logic should prefer get_or_create_flow for caching behavior.
         """
         logger.warning(f"Using get_flow_structure for mode '{mode_name}'. Consider using get_or_create_flow for caching.")
         mode_config = self._mode_configs.get(mode_name)
         if not mode_config:
             logger.error(f"Mode '{mode_name}' not found in validated configuration.")
             return None

         flow_creator_path = mode_config.get('_flow_creator_path')
         if not flow_creator_path:
             logger.error(f"Internal Error: Mode '{mode_name}' configuration missing '_flow_creator_path'. Cannot load flow.")
             return None

         try:
             module_path, func_name = flow_creator_path.rsplit('.', 1)
             module = importlib.import_module(module_path)
             create_flow_func = getattr(module, func_name)
             flow = create_flow_func()
             if not isinstance(flow, Flow):
                  logger.error(f"Flow creation function '{func_name}' from '{flow_creator_path}' did not return a PocketFlow Flow instance.")
                  return None
             return flow
         except Exception as e:
             logger.error(f"Failed to load or create flow structure from {flow_creator_path} for mode '{mode_name}': {e}", exc_info=True)
             return None
