# pocketcode/core/registration.py
import importlib
import logging
# Use Union for type hinting the registry value
from typing import Dict, Type, Any, Tuple, Union, Optional

# Keep BaseTool for tool registration, remove BaseMode
from pocketcode.core.interfaces import BaseTool

# Configure logging for registration process
logger = logging.getLogger(__name__)

# _import_class remains the same, only used for tools now
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


# Modified _load_and_register to handle modes differently
def _load_and_register(
    component_type: str, # 'modes' or 'tools'
    config: Dict[str, Any], # The full loaded settings dictionary
    # Registry type hint updated for modes
    registry: Dict[str, Union[Type, str]], # Stores Type for tools, str (path) for modes
    base_class: Optional[Type] = None # Base class only needed for tools now
):
    """Helper to load and register components (mode flow paths or tool classes) from config."""
    components_config = config.get(component_type, {})
    if not isinstance(components_config, dict):
        logger.warning(f"Invalid configuration structure for '{component_type}'. Expected a dictionary. Skipping registration.")
        return

    logger.info(f"Starting registration for {component_type}...")
    for component_key, component_details in components_config.items():
        component_name_or_slug = component_key # Use the key from settings.yaml

        if component_type == 'modes':
            if not isinstance(component_details, dict):
                logger.warning(f"Invalid configuration for mode '{component_key}'. Expected a dictionary containing mode details. Skipping.")
                continue
            # Expect 'flow_module' key pointing to the flow creation function path
            flow_module_path = component_details.get('flow_module')
            if not flow_module_path or not isinstance(flow_module_path, str):
                logger.warning(f"Missing or invalid 'flow_module' path string in configuration for mode '{component_key}'. Skipping.")
                continue

            # Register the path string directly
            if component_name_or_slug in registry:
                logger.warning(f"Duplicate mode key '{component_name_or_slug}' found from {flow_module_path}. Overwriting previous entry.")
            registry[component_name_or_slug] = flow_module_path # Store the path string
            logger.info(f"Registered Mode Flow Path: '{component_name_or_slug}' -> {flow_module_path}")

        elif component_type == 'tools':
            if not isinstance(component_details, str):
                logger.warning(f"Invalid configuration for tool '{component_key}'. Expected a module path string. Skipping.")
                continue
            tool_class_path = component_details

            # Import the tool class
            cls, class_name = _import_class(tool_class_path)
            if cls is None:
                continue # Error logged in _import_class

            # Check inheritance for tools
            if base_class and issubclass(cls, base_class):
                if component_name_or_slug in registry:
                    logger.warning(f"Duplicate tool key '{component_name_or_slug}' found from {tool_class_path}. Overwriting previous entry.")
                registry[component_name_or_slug] = cls # Store the class Type
                logger.info(f"Registered Tool Class: '{component_name_or_slug}' -> {tool_class_path}")
            else:
                logger.warning(f"{tool_class_path} (Class: {class_name}) is not a subclass of {base_class.__name__ if base_class else 'BaseTool'}. Skipping.")
        else:
             logger.error(f"Unknown component type '{component_type}' during registration.")
             continue # Should not happen


# Updated register_components function signature and logic
def register_components(config: Dict[str, Any]) -> Dict[str, Dict[str, Union[str, Type]]]:
    """
    Discovers and registers mode flow paths and tool classes based on configuration.

    Args:
        config: The loaded settings dictionary.

    Returns:
        A dictionary containing the registered mode flow paths and tool classes.
        Example: {'modes': {'koder': 'pocketcode.mode_flows.koder.create_code_flow'},
                  'tools': {'read_file': ReadFileToolClass}}
    """
    if not isinstance(config, dict):
        logger.error("Invalid configuration passed to register_components. Expected a dictionary.")
        return {"modes": {}, "tools": {}} # Return empty structure

    # Registry type hint updated
    registered: Dict[str, Dict[str, Union[str, Type]]] = {"modes": {}, "tools": {}}

    # Call helper for modes (no base class check needed)
    _load_and_register('modes', config, registered['modes'])
    # Call helper for tools (pass BaseTool for checking)
    _load_and_register('tools', config, registered['tools'], base_class=BaseTool) # Pass base_class explicitly

    logger.info(f"Registration complete. Mode Flow Paths registered: {len(registered['modes'])}. Tools registered: {len(registered['tools'])}.")
    return registered

# Example usage remains largely the same for illustration, but reflects the change for modes
if __name__ == "__main__":
    # Example with dummy config for structure testing
    dummy_config_correct = {
        "modes": {
            "dummy_mode": {
                 # Now expects flow_module path string
                 "flow_module": "some.path.to.create_dummy_flow"
            }
        },
        "tools": {
            "dummy_tool": "pocketcode.core.interfaces.BaseTool" # Tool path remains class path
        }
    }
    print("\nTesting registration with dummy config:")
    registered_dummy = register_components(dummy_config_correct)
    print("Modes (Flow Paths):", registered_dummy.get('modes', {})) # Show paths
    print("Tools (Classes):", list(registered_dummy.get('tools', {}).keys())) # Show tool keys

    # Other examples can be adjusted similarly if needed
    dummy_config_bad_tool = { "tools": { "bad_tool": {"module": "path"} } }
    print("\nTesting registration with bad tool config:")
    register_components(dummy_config_bad_tool)
    dummy_config_bad_mode = { "modes": { "bad_mode": "path.to.module" } }
    print("\nTesting registration with bad mode config:")
    register_components(dummy_config_bad_mode)
    dummy_config_missing_module = { "modes": { "missing_flow_module_mode": {"name": "Test"} } }
    print("\nTesting registration with missing flow_module key:")
    register_components(dummy_config_missing_module)