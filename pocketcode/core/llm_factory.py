import logging
from typing import Any, Dict, Optional

from pocketcode.core.interfaces import BaseLlmClient
from pocketcode.core.llm_providers import GeminiLlmProvider, OpenAICompatibleLlmProvider

logger = logging.getLogger(__name__)

OPENAI_COMPATIBLE_DEFAULT_BASE_URLS: Dict[str, str | None] = {
    "openai": None,
    "openrouter": "https://openrouter.ai/api/v1",
    "xai": "https://api.x.ai/v1",
    "requesty": "https://router.requesty.ai/v1",
}


def _resolve_provider_credentials(
    provider: str, providers_config: Dict[str, Any]
) -> tuple[str | None, str | None, Dict[str, Any]]:
    provider_entry = providers_config.get(provider)
    if isinstance(provider_entry, dict):
        api_key = provider_entry.get("api_key")
        base_url = provider_entry.get("base_url")
        extra_options = {
            key: value for key, value in provider_entry.items() if key not in {"api_key", "base_url"}
        }
        return (api_key, base_url, extra_options)
    return (provider_entry, None, {})


def _parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def create_llm_client(
    llm_config: Dict[str, Any], providers_config: Dict[str, Any]
) -> Optional[BaseLlmClient]:
    """
    Create an LLM client based on configured provider.

    Args:
        llm_config: LLM profile config with at least `provider`.
        providers_config: Provider secrets map from configuration.
    """
    provider = llm_config.get("provider")
    if not provider:
        logger.error("LLM configuration missing 'provider'. Cannot create client.")
        return None

    api_key, configured_base_url, provider_options = _resolve_provider_credentials(provider, providers_config)

    use_vertexai = _parse_bool(
        provider_options.get("use_vertexai", provider_options.get("vertexai", False)),
        default=False,
    )

    if provider != "gemini" and not api_key:
        logger.error(
            "API key configuration not found for provider '%s' in 'providers'.",
            provider,
        )
        return None
    if provider == "gemini" and not api_key and not use_vertexai:
        logger.error(
            "Gemini provider requires either an API key or `use_vertexai: true` with ADC credentials."
        )
        return None

    if isinstance(api_key, str) and api_key.startswith("${") and api_key.endswith("}"):
        logger.error(
            "Provider '%s' API key is unresolved (%s). Check environment variable loading.",
            provider,
            api_key,
        )
        return None

    logger.info("Attempting to create LLM client wrapper for provider: %s", provider)

    try:
        if provider == "gemini":
            client_wrapper = GeminiLlmProvider(
                api_key=api_key,
                use_vertexai=use_vertexai,
                project=provider_options.get("project"),
                location=provider_options.get("location"),
            )
            logger.info("Successfully created GeminiLlmProvider.")
            return client_wrapper

        if provider in OPENAI_COMPATIBLE_DEFAULT_BASE_URLS:
            default_base_url = OPENAI_COMPATIBLE_DEFAULT_BASE_URLS.get(provider)
            base_url = configured_base_url or default_base_url
            client_wrapper = OpenAICompatibleLlmProvider(
                provider_name=provider,
                api_key=api_key,
                base_url=base_url,
            )
            logger.info(
                "Successfully created OpenAICompatibleLlmProvider for provider '%s'.",
                provider,
            )
            return client_wrapper

        logger.error("Unsupported LLM provider specified: '%s'.", provider)
        return None
    except Exception as exc:
        logger.error(
            "Failed to initialize LLM client wrapper for provider '%s': %s",
            provider,
            exc,
            exc_info=True,
        )
        return None
