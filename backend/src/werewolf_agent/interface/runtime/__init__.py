"""Settings and observability bootstrap for interface processes."""

from werewolf_agent.interface.runtime.bootstrap import (
    configure_interface_logging,
    load_app_settings,
    settings_error_detail,
    settings_error_location,
)
from werewolf_agent.interface.runtime.observability import (
    bind_observation_context,
    configure_observability,
    get_observation_context,
)
from werewolf_agent.interface.runtime.settings import (
    APP_NAME,
    DEFAULT_GAME_DEFAULT_PLAYER_COUNT,
    DEFAULT_GAME_MAX_PLAYERS,
    DEFAULT_GAME_MIN_PLAYERS,
    DEFAULT_SQLITE_PATH,
    DEFAULT_STREAMLIT_LANGUAGE,
    PACKAGED_DEFAULTS,
    AppSettings,
    get_settings,
    repository_root,
    split_csv,
    split_mapping,
)

__all__ = [
    "APP_NAME",
    "DEFAULT_GAME_DEFAULT_PLAYER_COUNT",
    "DEFAULT_GAME_MAX_PLAYERS",
    "DEFAULT_GAME_MIN_PLAYERS",
    "DEFAULT_SQLITE_PATH",
    "DEFAULT_STREAMLIT_LANGUAGE",
    "PACKAGED_DEFAULTS",
    "AppSettings",
    "bind_observation_context",
    "configure_interface_logging",
    "configure_observability",
    "get_observation_context",
    "get_settings",
    "load_app_settings",
    "repository_root",
    "settings_error_detail",
    "settings_error_location",
    "split_csv",
    "split_mapping",
]
