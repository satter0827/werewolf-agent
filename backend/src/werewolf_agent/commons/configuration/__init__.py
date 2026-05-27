"""Public configuration entry points for interface adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from werewolf_agent.commons.configuration.defaults import (
    API_SERVICE_NAME,
    APP_NAME,
    DEFAULT_DJANGO_SECRET_KEY,
    DEFAULT_DJANGO_SQLITE_PATH,
    DEFAULT_DJANGO_STATIC_ROOT,
    DEFAULT_GAME_DEFAULT_PLAYER_COUNT,
    DEFAULT_GAME_DEFAULT_RULESET_DESCRIPTION,
    DEFAULT_GAME_DEFAULT_RULESET_ID,
    DEFAULT_GAME_DEFAULT_RULESET_NAME,
    DEFAULT_GAME_MAX_PLAYERS,
    DEFAULT_GAME_MIN_PLAYERS,
    DEFAULT_GAME_SUPPORTED_AGENT_NAME,
    DEFAULT_GAME_SUPPORTED_AGENT_TYPE,
    DEFAULT_GENERATED_DIR,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOG_LEVEL,
    DEFAULT_LOG_OUTPUT,
    MIN_DJANGO_SECRET_KEY_LENGTH,
)
from werewolf_agent.commons.configuration.settings import (
    LOG_FORMAT_NAMES,
    LOG_LEVEL_NAMES,
    LOG_OUTPUT_NAMES,
    AppSettings,
    LogFormat,
    LogOutput,
    get_settings,
    normalize_choice,
    normalize_non_blank,
    repository_root,
    split_csv,
)

if TYPE_CHECKING:
    from werewolf_agent.commons.configuration.usecase import build_game_usecase_settings


def __getattr__(name: str) -> Any:
    if name == "build_game_usecase_settings":
        from werewolf_agent.commons.configuration.usecase import build_game_usecase_settings

        return build_game_usecase_settings
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = [
    "API_SERVICE_NAME",
    "APP_NAME",
    "DEFAULT_DJANGO_SECRET_KEY",
    "DEFAULT_DJANGO_SQLITE_PATH",
    "DEFAULT_DJANGO_STATIC_ROOT",
    "DEFAULT_GAME_DEFAULT_PLAYER_COUNT",
    "DEFAULT_GAME_DEFAULT_RULESET_DESCRIPTION",
    "DEFAULT_GAME_DEFAULT_RULESET_ID",
    "DEFAULT_GAME_DEFAULT_RULESET_NAME",
    "DEFAULT_GAME_MAX_PLAYERS",
    "DEFAULT_GAME_MIN_PLAYERS",
    "DEFAULT_GAME_SUPPORTED_AGENT_NAME",
    "DEFAULT_GAME_SUPPORTED_AGENT_TYPE",
    "DEFAULT_GENERATED_DIR",
    "DEFAULT_LLM_MODEL",
    "DEFAULT_LLM_PROVIDER",
    "DEFAULT_LOG_FORMAT",
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_LOG_OUTPUT",
    "LOG_FORMAT_NAMES",
    "LOG_LEVEL_NAMES",
    "LOG_OUTPUT_NAMES",
    "MIN_DJANGO_SECRET_KEY_LENGTH",
    "AppSettings",
    "LogFormat",
    "LogOutput",
    "build_game_usecase_settings",
    "get_settings",
    "normalize_choice",
    "normalize_non_blank",
    "repository_root",
    "split_csv",
]
