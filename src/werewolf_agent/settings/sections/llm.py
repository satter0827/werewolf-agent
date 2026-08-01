"""llm runtime settings section."""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr

from werewolf_agent.settings.constants import (
    MAX_LLM_TEMPERATURE,
    MIN_LLM_TEMPERATURE,
    MIN_RETRY_COUNT,
    MIN_TIMEOUT_SECONDS_EXCLUSIVE,
)


class LlmSettings(BaseModel):
    """Settings owned by the llm runtime boundary."""

    llm_provider: str = Field(
        validation_alias="WEREWOLF_LLM_PROVIDER",
    )
    model: str = Field(validation_alias="WEREWOLF_MODEL")
    llm_base_url: str = Field(
        validation_alias="WEREWOLF_LLM_BASE_URL",
    )
    llm_timeout_seconds: float = Field(
        gt=MIN_TIMEOUT_SECONDS_EXCLUSIVE,
        validation_alias="WEREWOLF_LLM_TIMEOUT_SECONDS",
    )
    llm_max_retries: int = Field(
        ge=MIN_RETRY_COUNT,
        validation_alias="WEREWOLF_LLM_MAX_RETRIES",
    )
    llm_max_tokens: int = Field(
        ge=1,
        validation_alias="WEREWOLF_LLM_MAX_TOKENS",
    )
    llm_model_catalog_max_bytes: int = Field(
        ge=1,
        validation_alias="WEREWOLF_LLM_MODEL_CATALOG_MAX_BYTES",
    )
    llm_temperature: float = Field(
        ge=MIN_LLM_TEMPERATURE,
        le=MAX_LLM_TEMPERATURE,
        validation_alias="WEREWOLF_LLM_TEMPERATURE",
    )
    llm_prompt_file: str = Field(
        validation_alias="WEREWOLF_LLM_PROMPT_FILE",
    )
    llm_fake_responses_file: str = Field(
        validation_alias="WEREWOLF_LLM_FAKE_RESPONSES_FILE",
    )
    openai_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="OPENAI_API_KEY",
    )
