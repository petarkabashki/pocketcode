#%% pocketcode/core/llm_factory.py
import logging
import os
from typing import Dict, Any, Optional
from google import genai
# Import the base interface
from pocketcode.core.interfaces import BaseLlmClient


# TODO: Add imports for other providers (Anthropic, OpenAI) when wrappers are added

logger = logging.getLogger(__name__)

# --- Provider-Specific Wrapper Classes ---

class GeminiClientWrapper(BaseLlmClient):
    """Wrapper for the Google Gemini client implementing BaseLlmClient."""
    def __init__(self, api_key: str):
        if not genai:
            raise ImportError("Google Generative AI SDK ('google-genai') is required for GeminiClientWrapper.")
        # Correct initialization using genai.configure is often preferred,
        # but the user's example uses genai.Client, so we stick to that for now.
        # genai.configure(api_key=api_key)
        # self._model = genai.GenerativeModel(...) # Model selection happens in generate
        self._client = genai.Client(api_key=api_key) # Initialize the client as shown in user example
        logger.info("GeminiClientWrapper initialized.")

    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generates text using the Gemini API.

        Args:
            prompt: The input prompt string.
            **kwargs: Expected parameters:
                - model (str): The specific Gemini model name (e.g., 'models/gemini-1.5-flash'). Required.
                - temperature (float, optional)
                - top_p (float, optional)
                - top_k (int, optional)
                - max_output_tokens (int, optional)
                - safety_settings (list, optional): Provider-specific safety settings.

        Returns:
            The generated text response as a string.

        Raises:
            ValueError: If the required 'model' parameter is missing.
            Exception: Underlying exceptions from the genai SDK.
        """
        model_name = kwargs.get("model")
        if not model_name:
            raise ValueError("Missing required parameter 'model' for GeminiClientWrapper.generate()")

        # Ensure model name has the 'models/' prefix if not present, common requirement
        if not model_name.startswith('models/'):
             logger.warning(f"Model name '{model_name}' might be missing the 'models/' prefix. Prepending it.")
             model_name = f"models/{model_name}" # Or adjust based on exact SDK needs

        # Extract generation parameters from kwargs
        parameters = {
            'temperature': kwargs.get('temperature'),
            'top_p': kwargs.get('top_p'),
            'top_k': kwargs.get('top_k'),
            'candidate_count': 1, # Typically 1 for text generation
            'max_output_tokens': kwargs.get('max_output_tokens'),
            # 'stop_sequences': kwargs.get('stop_sequences') # Add if needed
        }
        # Filter out None values
        filtered_params = {k: v for k, v in parameters.items() if v is not None}

        gen_config = None
        if filtered_params:
            try:
                # Ensure correct type mapping if needed by GenerationConfig
                gen_config = genai.types.GenerationConfig(**filtered_params)
                logger.debug(f"Using GenerationConfig: {filtered_params}")
            except TypeError as e:
                 logger.error(f"Invalid parameter type for GenerationConfig: {e}. Params: {filtered_params}")
                 # Decide how to handle: raise error, use defaults, or proceed without config?
                 # For now, proceed without config if invalid.
                 gen_config = None


        # Extract safety settings if provided
        safety_settings = kwargs.get("safety_settings") # TODO: Define structure in config

        logger.debug(f"Calling Gemini model '{model_name}' via wrapper with prompt: '{prompt[:100]}...'")
        try:
            # *** MODIFIED CALL ***
            # Use the client instance and pass contents as a list
            response_object = self._client.generate_content( # Use generate_content directly on the client
                model=model_name,
                contents=[prompt], # Pass the prompt within a list as required
                generation_config=gen_config,
                safety_settings=safety_settings
                # stream=False # Default is False
            )
            # Extract text response - handle potential errors/blocks
            # Accessing parts might differ slightly with client.generate_content vs model.generate_content
            # Check response structure for safety blocks etc.
            if response_object.candidates:
                 response_text = response_object.text # Access text directly if available
            else:
                 # Handle cases with no candidates (e.g., blocked prompt)
                 logger.warning(f"Gemini response for model '{model_name}' had no candidates. Prompt might have been blocked.")
                 # Check for prompt feedback
                 prompt_feedback = getattr(response_object, 'prompt_feedback', None)
                 if prompt_feedback:
                     logger.warning(f"Prompt Feedback: {prompt_feedback}")
                 response_text = "" # Or raise an error

            logger.debug("Gemini API call successful via wrapper.")
            return response_text
        except Exception as e:
            logger.error(f"Gemini API call failed via wrapper: {e}", exc_info=True)
            raise # Re-raise the exception to be handled by the caller

# TODO: Implement wrappers for other providers (AnthropicClientWrapper, OpenAIClientWrapper)

# --- Factory Function ---

def create_llm_client(llm_config: Dict[str, Any], providers_config: Dict[str, Any]) -> Optional[BaseLlmClient]:
    """
    Creates an LLM client wrapper instance based on the provided configuration.

    Args:
        llm_config: Dictionary containing LLM settings (provider, model, parameters).
                    Expected keys: 'provider', 'model', 'parameters'.
        providers_config: Dictionary containing API keys for different providers.
                          Keys are provider names (e.g., 'gemini', 'anthropic').
                          Values are the API keys (can be env var placeholders like ${VAR_NAME}).

    Returns:
        An initialized LLM client wrapper object implementing BaseLlmClient,
        or None if initialization fails.
    """
    provider = llm_config.get('provider')
    # Model name and parameters are now primarily used by the wrapper's generate method,
    # but we still need the provider here to choose the correct wrapper.

    if not provider:
        logger.error("LLM configuration missing 'provider'. Cannot create client wrapper.")
        return None

    logger.info(f"Attempting to create LLM client wrapper for provider: {provider}")

    # --- Get API Key ---
    api_key_config = providers_config.get(provider)
    api_key = None
    if api_key_config:
        # Resolve API key from environment variable if specified like ${VAR_NAME}
        if isinstance(api_key_config, str) and api_key_config.startswith('${') and api_key_config.endswith('}'):
            env_var_name = api_key_config[2:-1]
            api_key = os.environ.get(env_var_name)
            if not api_key:
                logger.error(f"API key environment variable '{env_var_name}' for provider '{provider}' not found.")
                return None
            logger.debug(f"Using API key from environment variable '{env_var_name}' for provider '{provider}'.")
        else:
            # Allow direct key in config (less secure, use with caution)
            api_key = api_key_config
            logger.warning(f"Using API key directly from configuration for provider '{provider}'. Consider using environment variables.")
    else:
        logger.error(f"API key configuration not found for provider '{provider}' in 'providers' section.")
        return None

    # --- Instantiate Wrapper based on Provider ---
    client_wrapper: Optional[BaseLlmClient] = None
    try:
        if provider == 'gemini':
            if not genai:
                logger.error("Google Generative AI SDK ('google-genai') is not installed. Cannot create Gemini client wrapper.")
                return None
            client_wrapper = GeminiClientWrapper(api_key=api_key)
            logger.info(f"Successfully created GeminiClientWrapper.")

        # elif provider == 'anthropic':
        #     # Example: Add Anthropic wrapper creation logic here
        #     # try:
        #     #     from anthropic import Anthropic # Import specific client
        #     # except ImportError:
        #     #     logger.error("Anthropic SDK ('anthropic') is not installed.")
        #     #     return None
        #     # client_wrapper = AnthropicClientWrapper(api_key=api_key) # Assuming AnthropicClientWrapper exists
        #     # logger.info(f"Successfully created AnthropicClientWrapper.")
        #     pass # Placeholder

        # elif provider == 'openai':
        #     # Example: Add OpenAI wrapper creation logic here
        #     # try:
        #     #     from openai import OpenAI # Import specific client
        #     # except ImportError:
        #     #     logger.error("OpenAI SDK ('openai') is not installed.")
        #     #     return None
        #     # client_wrapper = OpenAIClientWrapper(api_key=api_key) # Assuming OpenAIClientWrapper exists
        #     # logger.info(f"Successfully created OpenAIClientWrapper.")
        #     pass # Placeholder

        else:
            logger.error(f"Unsupported LLM provider specified: '{provider}'. Cannot create wrapper.")
            return None

    except ImportError as e:
         logger.error(f"Failed to import SDK for provider '{provider}': {e}")
         return None
    except Exception as e:
        logger.error(f"Failed to initialize LLM client wrapper for provider '{provider}': {e}", exc_info=True)
        return None

    return client_wrapper