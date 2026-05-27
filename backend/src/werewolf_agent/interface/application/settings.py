"""Adapters from interface settings to use case configuration."""

from __future__ import annotations

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
