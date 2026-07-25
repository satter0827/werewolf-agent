"""streamlit runtime settings section."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field

from werewolf_agent.settings.constants import (
    MAX_GAME_LIST_LIMIT,
    MAX_TIMELINE_LIMIT,
    MIN_INTERVAL_SECONDS,
    MIN_INTERVAL_SECONDS_EXCLUSIVE,
    MIN_PAGE_LIMIT,
    MIN_STEP_LIMIT,
)
from werewolf_agent.settings.defaults import (
    DEFAULT_STREAMLIT_AUTO_ADVANCE_INTERVAL_SECONDS,
    DEFAULT_STREAMLIT_CSS_FILE,
    DEFAULT_STREAMLIT_DEFAULT_MANUAL_PLAYER_ID,
    DEFAULT_STREAMLIT_DEFAULT_SEED,
    DEFAULT_STREAMLIT_I18N_FILE,
    DEFAULT_STREAMLIT_INITIAL_SIDEBAR_STATE,
    DEFAULT_STREAMLIT_LANGUAGE,
    DEFAULT_STREAMLIT_MAX_AUTO_STEPS,
    DEFAULT_STREAMLIT_PAGE_TITLE,
    DEFAULT_STREAMLIT_RANDOM_SEED_MAX,
    DEFAULT_STREAMLIT_REFRESH_INTERVAL_SECONDS,
    DEFAULT_STREAMLIT_RUN_LIMIT,
    DEFAULT_STREAMLIT_SCREENS_FILE,
    DEFAULT_STREAMLIT_SERVICE_NAME,
    DEFAULT_STREAMLIT_TURN_LIMIT,
    StreamlitLanguage,
    StreamlitSidebarState,
)


class StreamlitSettings(BaseModel):
    """Settings owned by the streamlit runtime boundary."""

    streamlit_refresh_interval_seconds: float = Field(
        default=DEFAULT_STREAMLIT_REFRESH_INTERVAL_SECONDS,
        ge=MIN_INTERVAL_SECONDS,
        validation_alias="WEREWOLF_STREAMLIT_REFRESH_INTERVAL_SECONDS",
    )
    streamlit_turn_limit: int = Field(
        default=DEFAULT_STREAMLIT_TURN_LIMIT,
        ge=MIN_PAGE_LIMIT,
        le=MAX_TIMELINE_LIMIT,
        validation_alias="WEREWOLF_STREAMLIT_TURN_LIMIT",
    )
    streamlit_run_limit: int = Field(
        default=DEFAULT_STREAMLIT_RUN_LIMIT,
        ge=MIN_PAGE_LIMIT,
        le=MAX_GAME_LIST_LIMIT,
        validation_alias="WEREWOLF_STREAMLIT_RUN_LIMIT",
    )
    streamlit_max_auto_steps: int = Field(
        default=DEFAULT_STREAMLIT_MAX_AUTO_STEPS,
        ge=MIN_STEP_LIMIT,
        validation_alias="WEREWOLF_STREAMLIT_MAX_AUTO_STEPS",
    )
    streamlit_auto_advance_interval_seconds: float = Field(
        default=DEFAULT_STREAMLIT_AUTO_ADVANCE_INTERVAL_SECONDS,
        gt=MIN_INTERVAL_SECONDS_EXCLUSIVE,
        validation_alias="WEREWOLF_STREAMLIT_AUTO_ADVANCE_INTERVAL_SECONDS",
    )
    streamlit_initial_sidebar_state: StreamlitSidebarState = Field(
        default=cast(StreamlitSidebarState, DEFAULT_STREAMLIT_INITIAL_SIDEBAR_STATE),
        validation_alias="WEREWOLF_STREAMLIT_INITIAL_SIDEBAR_STATE",
    )
    streamlit_language: StreamlitLanguage = Field(
        default=cast(StreamlitLanguage, DEFAULT_STREAMLIT_LANGUAGE),
        validation_alias="WEREWOLF_STREAMLIT_LANGUAGE",
    )
    streamlit_i18n_file: str = Field(
        default=DEFAULT_STREAMLIT_I18N_FILE,
        validation_alias="WEREWOLF_STREAMLIT_I18N_FILE",
    )
    streamlit_css_file: str = Field(
        default=DEFAULT_STREAMLIT_CSS_FILE,
        validation_alias="WEREWOLF_STREAMLIT_CSS_FILE",
    )
    streamlit_screens_file: str = Field(
        default=DEFAULT_STREAMLIT_SCREENS_FILE,
        validation_alias="WEREWOLF_STREAMLIT_SCREENS_FILE",
    )
    streamlit_page_title: str = Field(
        default=DEFAULT_STREAMLIT_PAGE_TITLE,
        validation_alias="WEREWOLF_STREAMLIT_PAGE_TITLE",
    )
    streamlit_default_seed: int = Field(
        default=DEFAULT_STREAMLIT_DEFAULT_SEED,
        validation_alias="WEREWOLF_STREAMLIT_DEFAULT_SEED",
    )
    streamlit_random_seed_max: int = Field(
        default=DEFAULT_STREAMLIT_RANDOM_SEED_MAX,
        ge=1,
        validation_alias="WEREWOLF_STREAMLIT_RANDOM_SEED_MAX",
    )
    streamlit_default_manual_player_id: str = Field(
        default=DEFAULT_STREAMLIT_DEFAULT_MANUAL_PLAYER_ID,
        validation_alias="WEREWOLF_STREAMLIT_DEFAULT_MANUAL_PLAYER_ID",
    )
    streamlit_service_name: str = Field(
        default=DEFAULT_STREAMLIT_SERVICE_NAME,
        validation_alias="WEREWOLF_STREAMLIT_SERVICE_NAME",
    )
