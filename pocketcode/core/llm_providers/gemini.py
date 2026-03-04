from __future__ import annotations

import logging
from typing import Any, Dict

import google.genai as genai

from pocketcode.core.interfaces import BaseLlmClient

logger = logging.getLogger(__name__)


class LLMSafetyError(RuntimeError):
    """Raised when Gemini blocks a response for safety reasons."""


class GeminiLlmProvider(BaseLlmClient):
    """Gemini implementation of the BaseLlmClient interface."""

    def __init__(
        self,
        api_key: str | None,
        *,
        use_vertexai: bool = False,
        project: str | None = None,
        location: str | None = None,
    ):
        client_kwargs: Dict[str, Any] = {}
        if use_vertexai:
            client_kwargs["vertexai"] = True
            if project:
                client_kwargs["project"] = project
            if location:
                client_kwargs["location"] = location
        else:
            if not api_key:
                raise ValueError("Gemini API key is required when use_vertexai is false.")
            # Force API-key mode even if GOOGLE_GENAI_USE_VERTEXAI is set in the environment.
            client_kwargs["vertexai"] = False
            client_kwargs["api_key"] = api_key

        self._client = genai.Client(**client_kwargs)
        self.last_generation_info: Dict[str, Any] = {}
        logger.info("GeminiLlmProvider initialized.")

    def generate(self, prompt: str, **kwargs) -> str:
        model_name = kwargs.get("model")
        if not model_name:
            raise ValueError("Missing required parameter 'model' for GeminiLlmProvider.generate().")

        config_kwargs: Dict[str, Any] = {}
        for key in (
            "temperature",
            "top_p",
            "top_k",
            "max_output_tokens",
            "candidate_count",
            "stop_sequences",
            "safety_settings",
        ):
            value = kwargs.get(key)
            if value is not None:
                config_kwargs[key] = value

        request: Dict[str, Any] = {
            "model": model_name,
            "contents": prompt,
        }

        if config_kwargs:
            if hasattr(genai, "types") and hasattr(genai.types, "GenerateContentConfig"):
                request["config"] = genai.types.GenerateContentConfig(**config_kwargs)
            else:
                request["config"] = config_kwargs

        logger.debug("Calling Gemini model '%s'.", model_name)
        response = self._client.models.generate_content(**request)

        response_text = getattr(response, "text", None) or ""
        candidates = getattr(response, "candidates", None) or []
        if not response_text and candidates:
            first_candidate = candidates[0]
            finish_reason = str(getattr(first_candidate, "finish_reason", "")).upper()
            if "SAFETY" in finish_reason:
                raise LLMSafetyError(
                    "Gemini blocked the response due to safety filters. "
                    "Revise the prompt or lower-risk content."
                )

            content = getattr(first_candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            response_text = "".join(
                str(getattr(part, "text", ""))
                for part in parts
                if getattr(part, "text", None) is not None
            )

        usage_metadata = getattr(response, "usage_metadata", None)
        usage: Dict[str, Any] = {}
        if usage_metadata is not None:
            usage = {
                "prompt_tokens": getattr(usage_metadata, "prompt_token_count", None),
                "completion_tokens": getattr(usage_metadata, "candidates_token_count", None),
                "total_tokens": getattr(usage_metadata, "total_token_count", None),
            }

        self.last_generation_info = {
            "provider": "gemini",
            "model": model_name,
            "usage": usage,
        }

        logger.debug("Gemini call finished for model '%s'.", model_name)
        return response_text
