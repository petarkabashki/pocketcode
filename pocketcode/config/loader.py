# pocketcode/config/loader.py
import yaml
import os
from typing import Dict, Any

DEFAULT_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), 'settings.yaml')

def load_settings(settings_path: str = DEFAULT_SETTINGS_PATH) -> Dict[str, Any]:
    """
    Loads the application settings from the specified YAML file.

    Args:
        settings_path: The path to the settings YAML file. Defaults to
                       'settings.yaml' in the same directory as this loader.

    Returns:
        A dictionary containing the loaded settings.

    Raises:
        FileNotFoundError: If the settings file cannot be found.
        yaml.YAMLError: If there is an error parsing the YAML file.
    """
    if not os.path.exists(settings_path):
        raise FileNotFoundError(f"Settings file not found at: {settings_path}")

    try:
        with open(settings_path, 'r') as f:
            settings = yaml.safe_load(f)
        if settings is None: # Handle empty file case
            return {}
        # TODO: Add potential environment variable substitution here if needed
        # TODO: Add potential schema validation here if needed
        return settings
    except yaml.YAMLError as e:
        print(f"Error parsing settings file {settings_path}: {e}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred while loading settings from {settings_path}: {e}")
        raise

# Example usage (for testing purposes)
if __name__ == "__main__":
    try:
        loaded_settings = load_settings()
        print("Settings loaded successfully:")
        import json
        print(json.dumps(loaded_settings, indent=2))
    except Exception as e:
        print(f"Failed to load settings: {e}")