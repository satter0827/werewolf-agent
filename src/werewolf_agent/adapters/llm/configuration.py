"""Validated configuration for external decision-model adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from werewolf_agent.adapters.agents.constants import (
    LLM_PROVIDER_LMSTUDIO,
    LLM_PROVIDER_OPENAI,
)
from werewolf_agent.adapters.llm.messages import (
    message_field_must_be_at_least,
    message_field_must_be_between,
    message_field_must_be_greater_than,
    message_llm_base_url_required,
    message_openai_api_key_required,
)
from werewolf_agent.agents.validation import non_blank

MIN_TIMEOUT_SECONDS_EXCLUSIVE: Final = 0
MIN_LLM_MAX_TOKENS: Final = 1
MIN_LLM_TEMPERATURE: Final = 0
MAX_LLM_TEMPERATURE: Final = 2
MIN_MODEL_CATALOG_MAX_BYTES: Final = 1


@dataclass(frozen=True)
class LlmProviderConfig:
    """Connection and execution settings for one decision-model adapter."""

    provider: str
    model: str
    base_url: str
    api_key: str = field(repr=False)
    timeout_seconds: float
    max_tokens: int
    temperature: float
    model_catalog_max_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        """Validate and normalize provider settings."""
        provider = non_blank(self.provider, "llm provider").lower()
        model = non_blank(self.model, "llm model")
        base_url = self.base_url.strip()
        api_key = self.api_key.strip()
        if self.timeout_seconds <= MIN_TIMEOUT_SECONDS_EXCLUSIVE:
            raise ValueError(
                message_field_must_be_greater_than(
                    "llm timeout_seconds",
                    MIN_TIMEOUT_SECONDS_EXCLUSIVE,
                )
            )
        if self.max_tokens < MIN_LLM_MAX_TOKENS:
            raise ValueError(message_field_must_be_at_least("llm max_tokens", MIN_LLM_MAX_TOKENS))
        if not MIN_LLM_TEMPERATURE <= self.temperature <= MAX_LLM_TEMPERATURE:
            raise ValueError(
                message_field_must_be_between(
                    "llm temperature",
                    MIN_LLM_TEMPERATURE,
                    MAX_LLM_TEMPERATURE,
                )
            )
        if self.model_catalog_max_bytes < MIN_MODEL_CATALOG_MAX_BYTES:
            raise ValueError(
                message_field_must_be_at_least(
                    "llm model_catalog_max_bytes",
                    MIN_MODEL_CATALOG_MAX_BYTES,
                )
            )
        if provider == LLM_PROVIDER_LMSTUDIO and not base_url:
            raise ValueError(message_llm_base_url_required(LLM_PROVIDER_LMSTUDIO))
        if provider == LLM_PROVIDER_OPENAI and not api_key:
            raise ValueError(message_openai_api_key_required(LLM_PROVIDER_OPENAI))

        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "api_key", api_key)


__all__ = ["LlmProviderConfig"]
