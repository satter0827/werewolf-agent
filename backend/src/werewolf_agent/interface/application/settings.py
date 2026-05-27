"""Adapters from interface settings to use case settings."""

from __future__ import annotations

from werewolf_agent.interface.shared.settings import AppSettings, get_settings
from werewolf_agent.usecase.jobs import GameUseCaseSettings


def build_game_usecase_settings(settings: AppSettings | None = None) -> GameUseCaseSettings:
    """Return use case settings from interface settings."""
    app_settings = settings or get_settings()
    return GameUseCaseSettings(
        min_players=app_settings.game_min_players,
        max_players=app_settings.game_max_players,
        default_player_count=app_settings.game_default_player_count,
        supported_agent_type=app_settings.game_supported_agent_type,
        default_ruleset_id=app_settings.game_default_ruleset_id,
        default_ruleset_name=app_settings.game_default_ruleset_name,
        default_ruleset_description=_ruleset_description(app_settings),
        supported_agent_name=app_settings.game_supported_agent_name,
    )


def _ruleset_description(settings: AppSettings) -> str:
    return (
        f"{settings.game_min_players}〜{settings.game_max_players}"
        "人向けの最小同期 API ルールセットです。"
    )
