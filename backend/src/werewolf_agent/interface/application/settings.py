"""Adapters from interface settings to use case configuration."""

from __future__ import annotations

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
        default_ruleset_id=app_settings.game_default_ruleset_id,
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
    return LlmProviderConfig(
        provider=app_settings.llm_provider,
        model=app_settings.model,
        prompt_file=app_settings.llm_prompt_path,
        fake_responses_file=app_settings.llm_fake_responses_path,
    )
