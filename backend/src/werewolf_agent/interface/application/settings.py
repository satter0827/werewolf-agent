"""Adapters from interface settings to use case configuration."""

from __future__ import annotations

from werewolf_agent.commons.shared.constants import (
    LLM_PROVIDER_LMSTUDIO,
    LLM_STUDIO_API_KEY_PLACEHOLDER,
)
from werewolf_agent.commons.shared.definitions import GameDefinitions, LlmDefinitions
from werewolf_agent.interface.runtime import AppSettings, get_settings
from werewolf_agent.usecase.jobs import GameUseCaseConfig, LlmProviderConfig


def build_game_usecase_config(settings: AppSettings | None = None) -> GameUseCaseConfig:
    """Return use case configuration from interface settings.

    Args:
        settings: Optional preloaded application settings. When omitted, settings are loaded from
            the default runtime sources.

    Returns:
        Use case configuration without interface-only settings.

    """
    app_settings = settings or get_settings()
    return GameUseCaseConfig(
        min_players=app_settings.game_min_players,
        max_players=app_settings.game_max_players,
        default_player_count=app_settings.game_default_player_count,
        supported_agent_type=app_settings.game_supported_agent_type,
        default_setup_id=app_settings.game_default_setup_id,
        default_narration_mode=app_settings.game_default_narration_mode,
        game_list_default_limit=app_settings.api_game_list_default_limit,
        game_list_max_limit=app_settings.api_game_list_max_limit,
        timeline_default_limit=app_settings.api_timeline_default_limit,
        timeline_max_limit=app_settings.api_timeline_max_limit,
    )


def build_llm_provider_config(settings: AppSettings | None = None) -> LlmProviderConfig:
    """Return LLM provider configuration from interface settings.

    Args:
        settings: Optional preloaded application settings. When omitted, settings are loaded from
            the default runtime sources.

    Returns:
        LLM provider configuration for automated players.

    """
    app_settings = settings or get_settings()
    api_key = app_settings.configured_openai_api_key
    if app_settings.llm_provider == LLM_PROVIDER_LMSTUDIO and not api_key:
        api_key = LLM_STUDIO_API_KEY_PLACEHOLDER
    return LlmProviderConfig(
        provider=app_settings.llm_provider,
        model=app_settings.model,
        base_url=app_settings.llm_base_url,
        api_key=api_key,
        timeout_seconds=app_settings.llm_timeout_seconds,
        max_retries=app_settings.llm_max_retries,
        max_tokens=app_settings.llm_max_tokens,
        temperature=app_settings.llm_temperature,
        default_agent_strategy_id=app_settings.llm_default_agent_strategy_id,
        structured_output_mode=app_settings.llm_structured_output_mode,
        validation_retry_count=app_settings.llm_validation_retry_count,
        graph_max_steps=app_settings.llm_graph_max_steps,
        fallback_policy=app_settings.llm_fallback_policy,
    )


def build_game_definitions(settings: AppSettings | None = None) -> GameDefinitions:
    """Return loaded game definitions from interface runtime settings."""
    app_settings = settings or get_settings()
    return app_settings.game_definitions


def build_llm_definitions(settings: AppSettings | None = None) -> LlmDefinitions:
    """Return loaded LLM definitions from interface runtime settings."""
    app_settings = settings or get_settings()
    return app_settings.llm_definitions
