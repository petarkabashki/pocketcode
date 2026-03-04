from __future__ import annotations

import copy
import logging
from typing import Any, Dict

from pocketcode.core.llm_factory import create_llm_client

logger = logging.getLogger(__name__)


class LlmRouter:
    def __init__(
        self,
        config: Dict[str, Any],
        plugin_llm_profiles: Dict[str, Dict[str, Any]] | None = None,
    ):
        self._config = config
        llm_config = config.get("llm", {}) if isinstance(config, dict) else {}
        if not isinstance(llm_config, dict):
            llm_config = {}

        self._providers = llm_config.get("providers", {}) if isinstance(llm_config.get("providers"), dict) else {}
        self._clients: Dict[str, Any] = {}

        self._profiles: Dict[str, Dict[str, Any]] = {}
        self._pricing: Dict[str, Dict[str, float]] = {}
        self._last_generation_info: Dict[str, Any] = {}
        configured_profiles = llm_config.get("profiles", {})
        if isinstance(configured_profiles, dict):
            for profile_name, profile_config in configured_profiles.items():
                if isinstance(profile_config, dict):
                    self._profiles[str(profile_name)] = copy.deepcopy(profile_config)

        if plugin_llm_profiles:
            for profile_name, profile_config in plugin_llm_profiles.items():
                if isinstance(profile_config, dict):
                    self._profiles[str(profile_name)] = copy.deepcopy(profile_config)

        runtime_defaults = config.get("runtime", {}) if isinstance(config, dict) else {}
        raw_pricing = runtime_defaults.get("llm_pricing", {}) if isinstance(runtime_defaults, dict) else {}
        if isinstance(raw_pricing, dict):
            for model_name, pricing in raw_pricing.items():
                if not isinstance(model_name, str) or not isinstance(pricing, dict):
                    continue
                prompt_price = pricing.get("input_per_1k")
                completion_price = pricing.get("output_per_1k")
                parsed: Dict[str, float] = {}
                if isinstance(prompt_price, (int, float)):
                    parsed["input_per_1k"] = float(prompt_price)
                if isinstance(completion_price, (int, float)):
                    parsed["output_per_1k"] = float(completion_price)
                if parsed:
                    self._pricing[model_name] = parsed

        configured_default_profile = llm_config.get("default_profile")

        if configured_default_profile and str(configured_default_profile) in self._profiles:
            self.default_profile_name = str(configured_default_profile)
        elif "default" in self._profiles:
            self.default_profile_name = "default"
        elif self._profiles:
            self.default_profile_name = sorted(self._profiles.keys())[0]
        else:
            self.default_profile_name = None

    def list_profiles(self) -> Dict[str, Dict[str, Any]]:
        return copy.deepcopy(self._profiles)

    def resolve_profile_config(self, profile_name: str | None) -> Dict[str, Any]:
        effective_profile_name = profile_name or self.default_profile_name
        if not effective_profile_name:
            raise ValueError("No LLM profiles are configured.")

        if effective_profile_name in self._profiles:
            return copy.deepcopy(self._profiles[effective_profile_name])

        if ":" in effective_profile_name:
            provider, model = effective_profile_name.split(":", 1)
            return {
                "provider": provider,
                "model": model,
                "parameters": {},
            }

        raise KeyError(f"Unknown LLM profile '{effective_profile_name}'.")

    def generate(
        self,
        profile_name: str | None,
        prompt: str,
        parameter_overrides: Dict[str, Any] | None = None,
    ) -> str:
        profile = self.resolve_profile_config(profile_name)
        provider = profile.get("provider")
        model = profile.get("model")

        if not provider or not model:
            raise ValueError(f"Invalid LLM profile. Missing provider/model: {profile}")

        parameters = copy.deepcopy(profile.get("parameters", {}))
        if not isinstance(parameters, dict):
            parameters = {}
        if parameter_overrides:
            parameters.update(parameter_overrides)

        cache_key = f"{provider}:{model}"
        client = self._clients.get(cache_key)
        if not client:
            llm_config = {
                "provider": provider,
                "model": model,
                "parameters": parameters,
            }
            client = create_llm_client(llm_config, self._providers)
            if not client:
                raise RuntimeError(
                    f"Unable to initialize LLM client for profile '{profile_name or self.default_profile_name}'."
                )
            self._clients[cache_key] = client

        logger.debug("Calling LLM profile '%s' with model '%s'", profile_name, model)
        text = client.generate(prompt=prompt, model=model, **parameters)

        usage: Dict[str, Any] = {}
        if hasattr(client, "last_generation_info"):
            info = getattr(client, "last_generation_info")
            if isinstance(info, dict):
                usage_raw = info.get("usage", {})
                if isinstance(usage_raw, dict):
                    usage = usage_raw

        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")

        estimated_cost = self._estimate_cost(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        self._last_generation_info = {
            "profile_name": profile_name or self.default_profile_name,
            "provider": provider,
            "model": model,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            "estimated_cost_usd": estimated_cost,
        }
        return text

    def get_last_generation_info(self) -> Dict[str, Any]:
        return copy.deepcopy(self._last_generation_info)

    def _estimate_cost(
        self,
        *,
        model: str,
        prompt_tokens: Any,
        completion_tokens: Any,
    ) -> float:
        pricing = self._pricing.get(model, {})
        if not pricing:
            return 0.0

        input_per_1k = pricing.get("input_per_1k", 0.0)
        output_per_1k = pricing.get("output_per_1k", 0.0)

        prompt_count = float(prompt_tokens) if isinstance(prompt_tokens, (int, float)) else 0.0
        completion_count = float(completion_tokens) if isinstance(completion_tokens, (int, float)) else 0.0

        return (prompt_count / 1000.0) * input_per_1k + (completion_count / 1000.0) * output_per_1k
