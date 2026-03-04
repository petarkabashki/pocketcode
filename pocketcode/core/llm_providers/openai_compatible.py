from __future__ import annotations

import logging
from typing import Any, Dict

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime
    OpenAI = None

from pocketcode.core.interfaces import BaseLlmClient

logger = logging.getLogger(__name__)


class OpenAICompatibleLlmProvider(BaseLlmClient):
    """OpenAI-compatible chat completions provider."""

    def __init__(self, provider_name: str, api_key: str, base_url: str | None = None):
        if OpenAI is None:
            raise ImportError(
                "OpenAI SDK is required for OpenAI-compatible providers. Install dependency 'openai'."
            )
        self._provider_name = provider_name
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self.last_generation_info: Dict[str, Any] = {}
        logger.info(
            "OpenAICompatibleLlmProvider initialized for provider '%s' (base_url=%s).",
            provider_name,
            base_url or "default",
        )

    def generate(self, prompt: str, **kwargs) -> str:
        model_name = kwargs.get("model")
        if not model_name:
            raise ValueError(
                "Missing required parameter 'model' for OpenAICompatibleLlmProvider.generate()."
            )

        request: Dict[str, Any] = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
        }

        for key in ("temperature", "top_p", "max_tokens", "stop", "presence_penalty", "frequency_penalty"):
            value = kwargs.get(key)
            if value is not None:
                request[key] = value

        # Common alias used elsewhere in this project.
        if request.get("max_tokens") is None and kwargs.get("max_output_tokens") is not None:
            request["max_tokens"] = kwargs.get("max_output_tokens")

        logger.debug("Calling OpenAI-compatible model '%s' on provider '%s'.", model_name, self._provider_name)
        response = self._client.chat.completions.create(**request)

        text = ""
        choices = getattr(response, "choices", None) or []
        if choices:
            message = getattr(choices[0], "message", None)
            if message is not None:
                text = getattr(message, "content", "") or ""

        usage_raw = getattr(response, "usage", None)
        usage: Dict[str, Any] = {}
        if usage_raw is not None:
            usage = {
                "prompt_tokens": getattr(usage_raw, "prompt_tokens", None),
                "completion_tokens": getattr(usage_raw, "completion_tokens", None),
                "total_tokens": getattr(usage_raw, "total_tokens", None),
            }

        self.last_generation_info = {
            "provider": self._provider_name,
            "model": model_name,
            "usage": usage,
        }
        return text
