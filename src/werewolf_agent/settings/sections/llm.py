"""llm runtime settings section."""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr

from werewolf_agent.settings.constants import (
    MAX_LLM_TEMPERATURE,
    MIN_LLM_TEMPERATURE,
    MIN_RETRY_COUNT,
    MIN_STEP_LIMIT,
    MIN_TIMEOUT_SECONDS_EXCLUSIVE,
)
from werewolf_agent.settings.defaults import (
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_DECISION_GRAPHS_FILE,
    DEFAULT_LLM_DEFAULT_AGENT_STRATEGY_ID,
    DEFAULT_LLM_FAKE_RESPONSES_FILE,
    DEFAULT_LLM_FALLBACK_POLICY,
    DEFAULT_LLM_GRAPH_MAX_STEPS,
    DEFAULT_LLM_MAX_RETRIES,
    DEFAULT_LLM_MAX_TOKENS,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PLAYERS_FILE,
    DEFAULT_LLM_PROMPT_FILE,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_LLM_STRUCTURED_OUTPUT_MODE,
    DEFAULT_LLM_TEMPERATURE,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    DEFAULT_LLM_VALIDATION_RETRY_COUNT,
)


class LlmSettings(BaseModel):
    """Settings owned by the llm runtime boundary."""

    llm_provider: str = Field(
        default=DEFAULT_LLM_PROVIDER,
        validation_alias="WEREWOLF_LLM_PROVIDER",
    )
    model: str = Field(default=DEFAULT_LLM_MODEL, validation_alias="WEREWOLF_MODEL")
    llm_base_url: str = Field(
        default=DEFAULT_LLM_BASE_URL,
        validation_alias="WEREWOLF_LLM_BASE_URL",
    )
    llm_timeout_seconds: float = Field(
        default=DEFAULT_LLM_TIMEOUT_SECONDS,
        gt=MIN_TIMEOUT_SECONDS_EXCLUSIVE,
        validation_alias="WEREWOLF_LLM_TIMEOUT_SECONDS",
    )
    llm_max_retries: int = Field(
        default=DEFAULT_LLM_MAX_RETRIES,
        ge=MIN_RETRY_COUNT,
        validation_alias="WEREWOLF_LLM_MAX_RETRIES",
    )
    llm_max_tokens: int = Field(
        default=DEFAULT_LLM_MAX_TOKENS,
        ge=1,
        validation_alias="WEREWOLF_LLM_MAX_TOKENS",
    )
    llm_temperature: float = Field(
        default=DEFAULT_LLM_TEMPERATURE,
        ge=MIN_LLM_TEMPERATURE,
        le=MAX_LLM_TEMPERATURE,
        validation_alias="WEREWOLF_LLM_TEMPERATURE",
    )
    llm_default_agent_strategy_id: str = Field(
        default=DEFAULT_LLM_DEFAULT_AGENT_STRATEGY_ID,
        validation_alias="WEREWOLF_LLM_DEFAULT_AGENT_STRATEGY_ID",
    )
    llm_decision_graphs_file: str = Field(
        default=DEFAULT_LLM_DECISION_GRAPHS_FILE,
        validation_alias="WEREWOLF_LLM_DECISION_GRAPHS_FILE",
    )
    llm_structured_output_mode: str = Field(
        default=DEFAULT_LLM_STRUCTURED_OUTPUT_MODE,
        validation_alias="WEREWOLF_LLM_STRUCTURED_OUTPUT_MODE",
    )
    llm_validation_retry_count: int = Field(
        default=DEFAULT_LLM_VALIDATION_RETRY_COUNT,
        ge=MIN_RETRY_COUNT,
        validation_alias="WEREWOLF_LLM_VALIDATION_RETRY_COUNT",
    )
    llm_graph_max_steps: int = Field(
        default=DEFAULT_LLM_GRAPH_MAX_STEPS,
        ge=MIN_STEP_LIMIT,
        validation_alias="WEREWOLF_LLM_GRAPH_MAX_STEPS",
    )
    llm_fallback_policy: str = Field(
        default=DEFAULT_LLM_FALLBACK_POLICY,
        validation_alias="WEREWOLF_LLM_FALLBACK_POLICY",
    )
    llm_prompt_file: str = Field(
        default=DEFAULT_LLM_PROMPT_FILE,
        validation_alias="WEREWOLF_LLM_PROMPT_FILE",
    )
    llm_fake_responses_file: str = Field(
        default=DEFAULT_LLM_FAKE_RESPONSES_FILE,
        validation_alias="WEREWOLF_LLM_FAKE_RESPONSES_FILE",
    )
    llm_players_file: str = Field(
        default=DEFAULT_LLM_PLAYERS_FILE,
        validation_alias="WEREWOLF_LLM_PLAYERS_FILE",
    )
    openai_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="OPENAI_API_KEY",
    )
