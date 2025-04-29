# pocketcode/config/loader.py
import yaml
import os
import re
from typing import Dict, Any, Optional

DEFAULT_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), 'settings.yaml')

# %% Helper function for environment variable substitution
def _substitute_env_vars(value: Any) -> Any:
    """Recursively substitutes environment variables in strings."""
    if isinstance(value, str):
        # Simple ${VAR_NAME} substitution
        return os.path.expandvars(value)
        # More robust regex-based substitution if needed:
        # pattern = re.compile(r'\$\{(\w+)\}')
        # return pattern.sub(lambda match: os.environ.get(match.group(1), ''), value)
    elif isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]
    else:
        return value

# %% Updated load_settings function
def load_settings(settings_path: str = DEFAULT_SETTINGS_PATH) -> Dict[str, Any]:
    """
    Loads the application settings from the specified YAML file, resolves
    environment variables, and processes LLM configurations to inject API keys.

    Args:
        settings_path: The path to the settings YAML file. Defaults to
                       'settings.yaml' in the same directory as this loader.

    Returns:
        A dictionary containing the processed settings.

    Raises:
        FileNotFoundError: If the settings file cannot be found.
        yaml.YAMLError: If there is an error parsing the YAML file.
        KeyError: If a required provider key is missing or misconfigured.
        ValueError: If LLM configuration is invalid.
    """
    if not os.path.exists(settings_path):
        raise FileNotFoundError(f"Settings file not found at: {settings_path}")

    try:
        with open(settings_path, 'r') as f:
            raw_settings = yaml.safe_load(f)
        if raw_settings is None: # Handle empty file case
            return {}

        # 1. Substitute environment variables globally
        settings = _substitute_env_vars(raw_settings)

        # 2. Process LLM configurations
        providers = settings.get('providers', {})
        defaults = settings.get('defaults', {})
        default_llm_config = defaults.get('llm_config', {})

        if 'modes' in settings and isinstance(settings['modes'], dict):
            for mode_slug, mode_config in settings['modes'].items():
                if not isinstance(mode_config, dict):
                    continue # Skip invalid mode configs

                # Determine effective LLM config (mode override or default)
                mode_llm_config = mode_config.get('llm_config', {})
                effective_llm_config = default_llm_config.copy()
                effective_llm_config.update(mode_llm_config) # Mode settings override defaults

                # Get the provider for this mode
                provider_name = effective_llm_config.get('provider')
                if not provider_name:
                    # If no provider specified even in defaults, skip or raise error
                    # For now, we assume defaults will have a provider if modes don't
                    if 'provider' not in default_llm_config:
                         print(f"Warning: No LLM provider specified for mode '{mode_slug}' or in defaults. Skipping API key injection.")
                         continue
                    provider_name = default_llm_config.get('provider')


                # Fetch API key from the central providers section
                api_key = providers.get(provider_name)
                if not api_key:
                    # Allow modes without API keys if provider isn't listed (e.g., local models)
                    # Or raise an error if a key is expected but missing:
                    # raise KeyError(f"API key for provider '{provider_name}' (used by mode '{mode_slug}') not found in 'providers' section.")
                    print(f"Warning: API key for provider '{provider_name}' (mode '{mode_slug}') not found in 'providers'. LLM might fail if key is required.")
                    # Remove any potentially lingering 'api_key' field from previous structure
                    effective_llm_config.pop('api_key', None)
                else:
                    # Inject the API key
                    effective_llm_config['api_key'] = api_key

                # Update the mode's config with the processed LLM details
                # Ensure llm_config exists in the mode's dictionary
                if 'llm_config' not in mode_config:
                    mode_config['llm_config'] = {}
                mode_config['llm_config'] = effective_llm_config # Replace/update mode's llm_config

        # TODO: Add potential schema validation here if needed
        return settings

    except yaml.YAMLError as e:
        print(f"Error parsing settings file {settings_path}: {e}")
        raise
    except KeyError as e:
        print(f"Configuration Error: Missing key - {e}")
        raise
    except ValueError as e:
        print(f"Configuration Error: Invalid value - {e}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred while loading settings from {settings_path}: {e}")
        raise

# Example usage (for testing purposes)
if __name__ == "__main__":
    try:
        # Assume settings.yaml is in the same directory for testing
        test_settings_path = os.path.join(os.path.dirname(__file__), 'settings.yaml')
        # Set dummy env vars for testing
        os.environ['GOOGLE_API_KEY'] = 'TEST_GOOGLE_KEY_123'
        os.environ['ANTHROPIC_API_KEY'] = 'TEST_ANTHROPIC_KEY_456'

        loaded_settings = load_settings(test_settings_path)
        print("Settings loaded and processed successfully:")
        import json
        # Use default=str for any non-serializable objects if necessary
        print(json.dumps(loaded_settings, indent=2, default=str))

        # Clean up dummy env vars
        del os.environ['GOOGLE_API_KEY']
        del os.environ['ANTHROPIC_API_KEY']

    except Exception as e:
        print(f"Failed to load settings: {e}")