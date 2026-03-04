# pocketcode/core/registration.py
import importlib
import logging
from typing import Dict, Type, Any, Tuple, Union, Optional

from pocketcode.core.interfaces import BaseTool

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
    except ValueError:
        logger.error(f"Invalid component path format for {component_path}.")
        return None, None
    except Exception as e:
        logger.error(f"An unexpected error occurred importing {component_path}: {e}")
        return None, None


def _load_and_register(
    component_type: str,
    config: Dict[str, Any],
    registry: Dict[str, Union[Type, str]],
    base_class: Optional[Type] = None
):
    """Helper to load and register tool classes from config."""
    components_config = config.get(component_type, {})
    if not isinstance(components_config, dict):
        logger.warning(f"Invalid configuration structure for '{component_type}'. Expected a dictionary. Skipping registration.")
        return

    logger.info(f"Starting registration for {component_type}...")
    for component_key, component_details in components_config.items():
        component_name_or_slug = component_key

        if component_type == 'tools':
            if not isinstance(component_details, str):
                logger.warning(f"Invalid configuration for tool '{component_key}'. Expected a module path string. Skipping.")
                continue
            tool_class_path = component_details

            cls, class_name = _import_class(tool_class_path)
            if cls is None:
                continue

            if base_class and issubclass(cls, base_class):
                if component_name_or_slug in registry:
                    logger.warning(f"Duplicate tool key '{component_name_or_slug}' found from {tool_class_path}. Overwriting previous entry.")
                registry[component_name_or_slug] = cls
                logger.info(f"Registered Tool Class: '{component_name_or_slug}' -> {tool_class_path}")
            else:
                logger.warning(f"{tool_class_path} (Class: {class_name}) is not a subclass of {base_class.__name__ if base_class else 'BaseTool'}. Skipping.")
        else:
            logger.error(f"Unknown component type '{component_type}' during registration.")
            continue


def register_components(config: Dict[str, Any]) -> Dict[str, Dict[str, Union[str, Type]]]:
    """
    Discovers and registers tool classes based on configuration.

    Args:
        config: The loaded settings dictionary.

    Returns:
        A dictionary containing registered tool classes.
        Example: {'modes': {}, 'tools': {'read_file': ReadFileToolClass}}
    """
    if not isinstance(config, dict):
        logger.error("Invalid configuration passed to register_components. Expected a dictionary.")
        return {"modes": {}, "tools": {}}

    registered: Dict[str, Dict[str, Union[str, Type]]] = {"modes": {}, "tools": {}}

    _load_and_register('tools', config, registered['tools'], base_class=BaseTool)

    logger.info(f"Registration complete. Tools registered: {len(registered['tools'])}.")
    return registered
