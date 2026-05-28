"""Adapters from interface settings to use case configuration."""

from __future__ import annotations

from typing import cast

from werewolf_agent.domain.llm import FakeLlmConfig, FakeLlmStrategy
from werewolf_agent.interface.shared.settings import AppSettings, get_settings
from werewolf_agent.usecase.jobs import GameUseCaseConfig


def build_game_usecase_config(settings: AppSettings | None = None) -> GameUseCaseConfig:
    """Return use case configuration from interface settings."""
    app_settings = settings or get_settings()
    return GameUseCaseConfig(
        min_players=app_settings.game_min_players,
        max_players=app_settings.game_max_players,
        default_player_count=app_settings.game_default_player_count,
        supported_agent_type=app_settings.game_supported_agent_type,
        default_ruleset_id=app_settings.game_default_ruleset_id,
    )


def build_fake_llm_config(settings: AppSettings | None = None) -> FakeLlmConfig:
    """Return FakeLLM configuration from interface settings."""
    app_settings = settings or get_settings()
    return FakeLlmConfig(
        strategy=cast(FakeLlmStrategy, app_settings.fake_llm_strategy),
        randomness=app_settings.fake_llm_randomness,
        persona_profiles=tuple(app_settings.fake_llm_persona_profile_list),
        speech_intents=tuple(app_settings.fake_llm_speech_intent_list),
        speech_templates=tuple(app_settings.fake_llm_speech_template_list),
        reason_templates=tuple(app_settings.fake_llm_reason_template_list),
    )
