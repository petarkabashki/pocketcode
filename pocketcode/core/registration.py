# pocketcode/core/registration.py
import importlib
import logging
from typing import Dict, Type, Any, Tuple

from pocketcode.core.interfaces import BaseMode, BaseTool

# Configure logging for registration process
logger = logging.getLogger(__name__)

def _import_class(component_path: str) -> Tuple[Type | None, str | None]:
    """Imports a class dynamically from a module path string."""
    if not isinstance(component_path, str) or '.' not in component_path:
        logger.warning(f"Invalid component path format '{component_path}'. Skipping import.")
        return None, None
    try:
        module_path, class_name = component_path.rsplit('.', 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)

        if not isinstance(cls, type):
            logger.warning(f"{component_path} did not resolve to a class. Skipping import.")
            return None, None
        return cls, class_name
    except ImportError:
        logger.error(f"Could not import module for {component_path}. Check PYTHONPATH and module existence.")
        return None, None
    except AttributeError:
        logger.error(f"Class '{class_name}' not found in module '{module_path}' for {component_path}.")
        return None, None
    except ValueError: # Handles rsplit error if '.' not found
        logger.error(f"Invalid component path format for {component_path}.")
        return None, None
    except Exception as e: # Catch-all for unexpected errors during import
        logger.error(f"An unexpected error occurred importing {component_path}: {e}")
        return None, None


def _load_and_register(
    component_type: str, # 'modes' or 'tools'
    config: Dict[str, Any], # The full loaded settings dictionary
    registry: Dict[str, Type], # The specific registry for modes or tools
    base_class: Type # BaseMode or BaseTool
):
    """Helper to load and register components (modes or tools) from config."""
    components_config = config.get(component_type, {})
    if not isinstance(components_config, dict):
        logger.warning(f"Invalid configuration structure for '{component_type}'. Expected a dictionary. Skipping registration.")
        return

    logger.info(f"Starting registration for {component_type}...")
    for component_key, component_details in components_config.items():
        component_path = None
        component_name_or_slug = component_key # Use the key from settings.yaml

        # Determine the module path based on component type
        if component_type == 'modes':
            if not isinstance(component_details, dict):
                logger.warning(f"Invalid configuration for mode '{component_key}'. Expected a dictionary containing mode details. Skipping.")
                continue
            component_path = component_details.get('module')
            if not component_path or not isinstance(component_path, str):
                logger.warning(f"Missing or invalid 'module' path string in configuration for mode '{component_key}'. Skipping.")
                continue
            # component_name_or_slug is already the mode slug (component_key)
        elif component_type == 'tools':
            if not isinstance(component_details, str):
                logger.warning(f"Invalid configuration for tool '{component_key}'. Expected a module path string. Skipping.")
                continue
            component_path = component_details
            # component_name_or_slug is already the tool name (component_key)
        else:
             logger.error(f"Unknown component type '{component_type}' during registration.")
             continue # Should not happen

        # Import the class
        cls, class_name = _import_class(component_path)
        if cls is None:
            continue # Error logged in _import_class

        # Check inheritance and register
        if issubclass(cls, base_class):
            if component_name_or_slug in registry:
                logger.warning(f"Duplicate {component_type[:-1]} key '{component_name_or_slug}' found from {component_path}. Overwriting previous entry.")

            registry[component_name_or_slug] = cls
            logger.info(f"Registered {component_type[:-1].capitalize()}: '{component_name_or_slug}' -> {component_path}")
        else:
            logger.warning(f"{component_path} (Class: {class_name}) is not a subclass of {base_class.__name__}. Skipping.")


def register_components(config: Dict[str, Any]) -> Dict[str, Dict[str, Type]]:
    """
    Discovers and registers modes and tools based on the provided configuration.

    Args:
        config: The loaded settings dictionary.

    Returns:
        A dictionary containing the registered modes and tools, keyed by their
        slug (for modes) or name (for tools), mapping to their respective classes.
        Example: {'modes': {'code': CodeModeClass}, 'tools': {'read_file': ReadFileToolClass}}
    """
    if not isinstance(config, dict):
        logger.error("Invalid configuration passed to register_components. Expected a dictionary.")
        return {"modes": {}, "tools": {}} # Return empty structure

    registered: Dict[str, Dict[str, Type]] = {"modes": {}, "tools": {}}

    # Pass the full config dictionary to the helper
    _load_and_register('modes', config, registered['modes'], BaseMode)
    _load_and_register('tools', config, registered['tools'], BaseTool)

    logger.info(f"Registration complete. Modes registered: {len(registered['modes'])}. Tools registered: {len(registered['tools'])}.")
    return registered

# Example usage (assuming config is loaded elsewhere)
if __name__ == "__main__":
    # This is illustrative; normally you'd load config first
    # from pocketcode.config.loader import load_settings
    # try:
    #     loaded_config = load_settings()
    #     registered_items = register_components(loaded_config)
    #     print("\nRegistered Components:")
    #     import json
    #     # Cannot directly JSON serialize types, so print keys
    #     print("Modes:", list(registered_items.get('modes', {}).keys()))
    #     print("Tools:", list(registered_items.get('tools', {}).keys()))
    # except Exception as e:
    #     print(f"Failed during example registration: {e}")

    # Example with dummy config for structure testing
    dummy_config_correct = {
        "modes": {
            "dummy_mode": {
                 "module": "pocketcode.core.interfaces.BaseMode" # Correct structure
            }
        },
        "tools": {
            "dummy_tool": "pocketcode.core.interfaces.BaseTool" # Correct structure
        }
    }
    print("\nTesting registration with dummy config:")
    registered_dummy = register_components(dummy_config_correct)
    print("Modes:", list(registered_dummy.get('modes', {}).keys()))
    print("Tools:", list(registered_dummy.get('tools', {}).keys()))
    # Example with incorrect tool structure
    dummy_config_bad_tool = { "tools": { "bad_tool": {"module": "path"} } }
    print("\nTesting registration with bad tool config:")
    register_components(dummy_config_bad_tool)
    # Example with incorrect mode structure
    dummy_config_bad_mode = { "modes": { "bad_mode": "path.to.module" } }
    print("\nTesting registration with bad mode config:")
    register_components(dummy_config_bad_mode)
    # Example with missing module key in mode
    dummy_config_missing_module = { "modes": { "missing_module_mode": {"name": "Test"} } }
    print("\nTesting registration with missing module key:")
    register_components(dummy_config_missing_module)