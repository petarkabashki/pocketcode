# pocketcode/config/loader.py
import os
import re
import logging
from pathlib import Path
from typing import Dict, Any

import yaml

WORKSPACE_SETTINGS_FILENAME = "pocketcode.yml"
logger = logging.getLogger(__name__)

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


def _contains_unresolved_env_vars(value: Any) -> bool:
    pattern = re.compile(r"\$\{[^}]+\}")
    if isinstance(value, str):
        return bool(pattern.search(value))
    if isinstance(value, dict):
        return any(_contains_unresolved_env_vars(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_unresolved_env_vars(item) for item in value)
    return False

# %% Updated load_settings function
def resolve_settings_path(settings_path: str | None = None, workspace_root: str | None = None) -> str:
    """
    Resolves which settings file to load.

    Resolution order:
    1. `<workspace_root>/pocketcode.yml`.
    """
    root = Path(workspace_root or os.getcwd())
    candidate = root / WORKSPACE_SETTINGS_FILENAME
    if not candidate.exists():
        raise FileNotFoundError(
            f"Workspace config file is required at: {candidate}. "
            "Create pocketcode.yml in the workspace root."
        )
    return str(candidate)


def load_settings(settings_path: str | None = None, workspace_root: str | None = None) -> Dict[str, Any]:
    """
    Loads the application settings from a resolved YAML file, resolves
    environment variables, and processes LLM configurations to inject API keys.

    Args:
        settings_path: Ignored. Configuration is always loaded from `<workspace_root>/pocketcode.yml`.
        workspace_root: Workspace root used to locate `pocketcode.yml`.

    Returns:
        A dictionary containing the processed settings.

    Raises:
        FileNotFoundError: If the settings file cannot be found.
        yaml.YAMLError: If there is an error parsing the YAML file.
        KeyError: If a required provider key is missing or misconfigured.
        ValueError: If LLM configuration is invalid.
    """
    resolved_settings_path = resolve_settings_path(settings_path=settings_path, workspace_root=workspace_root)

    if not os.path.exists(resolved_settings_path):
        raise FileNotFoundError(f"Settings file not found at: {resolved_settings_path}")

    try:
        with open(resolved_settings_path, 'r') as f:
            raw_settings = yaml.safe_load(f)
        if raw_settings is None: # Handle empty file case
            return {}

        # 1. Substitute environment variables globally
        settings = _substitute_env_vars(raw_settings)

        # 2. Validate LLM structure
        llm = settings.get("llm")
        if not isinstance(llm, dict):
            raise ValueError("Configuration must contain an 'llm' mapping.")

        providers = llm.get("providers")
        profiles = llm.get("profiles")
        if not isinstance(providers, dict):
            raise ValueError("Configuration must contain 'llm.providers' as a mapping.")
        if not isinstance(profiles, dict):
            raise ValueError("Configuration must contain 'llm.profiles' as a mapping.")

        if _contains_unresolved_env_vars(settings):
            raise ValueError(
                "Configuration contains unresolved environment variable placeholders like ${VAR_NAME}. "
                "Set required environment variables before starting Pocketcode."
            )

        # TODO: Add potential schema validation here if needed
        return settings

    except yaml.YAMLError as e:
        logger.error(f"Error parsing settings file {resolved_settings_path}: {e}")
        raise
    except KeyError as e:
        logger.error(f"Configuration Error: Missing key - {e}")
        raise
    except ValueError as e:
        logger.error(f"Configuration Error: Invalid value - {e}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading settings from {resolved_settings_path}: {e}")
        raise

# Example usage (for testing purposes)
if __name__ == "__main__":
    try:
        # Load the workspace settings file for testing.
        test_settings_path = os.path.join(os.getcwd(), 'pocketcode.yml')
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
