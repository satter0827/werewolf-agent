"""Validated runtime configuration for automated players."""

from __future__ import annotations

from dataclasses import dataclass, field

from werewolf_agent.agents.constants import (
    LLM_FALLBACK_POLICY_CHOICE_SET,
    LLM_PROVIDER_LMSTUDIO,
    LLM_PROVIDER_OPENAI,
    LLM_STRUCTURED_OUTPUT_MODE_CHOICE_SET,
    MAX_LLM_TEMPERATURE,
    MIN_LLM_MAX_TOKENS,
    MIN_LLM_TEMPERATURE,
    MIN_RETRY_COUNT,
    MIN_STEP_LIMIT,
    MIN_TIMEOUT_SECONDS_EXCLUSIVE,
)
from werewolf_agent.agents.messages import (
    message_field_must_be_at_least,
    message_field_must_be_between,
    message_field_must_be_greater_than,
    message_field_must_be_one_of,
    message_llm_base_url_required,
    message_openai_api_key_required,
)
from werewolf_agent.agents.validation import non_blank


@dataclass(frozen=True)
class LlmProviderConfig:
    """Connection and execution settings for a LangChain-backed player."""

    provider: str
    model: str
    base_url: str
    api_key: str = field(repr=False)
    timeout_seconds: float
    max_retries: int
    max_tokens: int
    temperature: float
    default_agent_strategy_id: str
    structured_output_mode: str
    validation_retry_count: int
    graph_max_steps: int
    fallback_policy: str

    def __post_init__(self) -> None:
        """Validate and normalize provider settings."""
        provider = non_blank(self.provider, "llm provider").lower()
        model = non_blank(self.model, "llm model")
        base_url = self.base_url.strip()
        api_key = self.api_key.strip()
        default_agent_strategy_id = non_blank(
            self.default_agent_strategy_id,
            "llm default_agent_strategy_id",
        )
        structured_output_mode = non_blank(
            self.structured_output_mode,
            "llm structured_output_mode",
        ).lower()
        fallback_policy = non_blank(self.fallback_policy, "llm fallback_policy").lower()
        if self.timeout_seconds <= MIN_TIMEOUT_SECONDS_EXCLUSIVE:
            raise ValueError(
                message_field_must_be_greater_than(
                    "llm timeout_seconds",
                    MIN_TIMEOUT_SECONDS_EXCLUSIVE,
                )
            )
        if self.max_retries < MIN_RETRY_COUNT:
            raise ValueError(message_field_must_be_at_least("llm max_retries", MIN_RETRY_COUNT))
        if self.validation_retry_count < MIN_RETRY_COUNT:
            raise ValueError(
                message_field_must_be_at_least(
                    "llm validation_retry_count",
                    MIN_RETRY_COUNT,
                )
            )
        if self.graph_max_steps < MIN_STEP_LIMIT:
            raise ValueError(message_field_must_be_at_least("llm graph_max_steps", MIN_STEP_LIMIT))
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
        if provider == LLM_PROVIDER_LMSTUDIO and not base_url:
            raise ValueError(message_llm_base_url_required(LLM_PROVIDER_LMSTUDIO))
        if provider == LLM_PROVIDER_OPENAI and not api_key:
            raise ValueError(message_openai_api_key_required(LLM_PROVIDER_OPENAI))
        if structured_output_mode not in LLM_STRUCTURED_OUTPUT_MODE_CHOICE_SET:
            raise ValueError(
                message_field_must_be_one_of(
                    "llm structured_output_mode",
                    LLM_STRUCTURED_OUTPUT_MODE_CHOICE_SET,
                )
            )
        if fallback_policy not in LLM_FALLBACK_POLICY_CHOICE_SET:
            raise ValueError(
                message_field_must_be_one_of(
                    "llm fallback_policy",
                    LLM_FALLBACK_POLICY_CHOICE_SET,
                )
            )

        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "default_agent_strategy_id", default_agent_strategy_id)
        object.__setattr__(self, "structured_output_mode", structured_output_mode)
        object.__setattr__(self, "fallback_policy", fallback_policy)


__all__ = ["LlmProviderConfig"]
