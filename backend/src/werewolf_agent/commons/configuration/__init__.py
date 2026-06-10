"""Settings and observability bootstrap for entry point processes."""

from werewolf_agent.commons.configuration.bootstrap import (
    configure_entrypoint_logging,
    load_app_settings,
    settings_error_detail,
    settings_error_location,
)
from werewolf_agent.commons.configuration.settings import (
    APP_NAME,
    DEFAULT_GAME_DEFAULT_PLAYER_COUNT,
    DEFAULT_GAME_MAX_PLAYERS,
    DEFAULT_GAME_MIN_PLAYERS,
    DEFAULT_STREAMLIT_CSS_FILE,
    DEFAULT_STREAMLIT_LANGUAGE,
    DEFAULT_STREAMLIT_RANDOM_SEED_MAX,
    DEFAULT_STREAMLIT_SCREENS_FILE,
    PACKAGED_DEFAULTS,
    AppSettings,
    get_settings,
    repository_root,
    split_csv,
    split_mapping,
)
from werewolf_agent.commons.observability import (
    bind_observation_context,
    configure_observability,
    get_observation_context,
)

__all__ = [
    "APP_NAME",
    "DEFAULT_GAME_DEFAULT_PLAYER_COUNT",
    "DEFAULT_GAME_MAX_PLAYERS",
    "DEFAULT_GAME_MIN_PLAYERS",
    "DEFAULT_STREAMLIT_CSS_FILE",
    "DEFAULT_STREAMLIT_LANGUAGE",
    "DEFAULT_STREAMLIT_RANDOM_SEED_MAX",
    "DEFAULT_STREAMLIT_SCREENS_FILE",
    "PACKAGED_DEFAULTS",
    "AppSettings",
    "bind_observation_context",
    "configure_entrypoint_logging",
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
