"""streamlit runtime settings section."""

from __future__ import annotations

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
    StreamlitLanguage,
    StreamlitSidebarState,
)


class StreamlitSettings(BaseModel):
    """Settings owned by the streamlit runtime boundary."""

    streamlit_refresh_interval_seconds: float = Field(
        ge=MIN_INTERVAL_SECONDS,
        validation_alias="WEREWOLF_STREAMLIT_REFRESH_INTERVAL_SECONDS",
    )
    streamlit_turn_limit: int = Field(
        ge=MIN_PAGE_LIMIT,
        le=MAX_TIMELINE_LIMIT,
        validation_alias="WEREWOLF_STREAMLIT_TURN_LIMIT",
    )
    streamlit_run_limit: int = Field(
        ge=MIN_PAGE_LIMIT,
        le=MAX_GAME_LIST_LIMIT,
        validation_alias="WEREWOLF_STREAMLIT_RUN_LIMIT",
    )
    streamlit_max_auto_steps: int = Field(
        ge=MIN_STEP_LIMIT,
        validation_alias="WEREWOLF_STREAMLIT_MAX_AUTO_STEPS",
    )
    streamlit_auto_advance_interval_seconds: float = Field(
        gt=MIN_INTERVAL_SECONDS_EXCLUSIVE,
        validation_alias="WEREWOLF_STREAMLIT_AUTO_ADVANCE_INTERVAL_SECONDS",
    )
    streamlit_initial_sidebar_state: StreamlitSidebarState = Field(
        validation_alias="WEREWOLF_STREAMLIT_INITIAL_SIDEBAR_STATE",
    )
    streamlit_language: StreamlitLanguage = Field(
        validation_alias="WEREWOLF_STREAMLIT_LANGUAGE",
    )
    streamlit_i18n_file: str = Field(
        validation_alias="WEREWOLF_STREAMLIT_I18N_FILE",
    )
    streamlit_page_title: str = Field(
        validation_alias="WEREWOLF_STREAMLIT_PAGE_TITLE",
    )
    streamlit_default_seed: int = Field(
        validation_alias="WEREWOLF_STREAMLIT_DEFAULT_SEED",
    )
    streamlit_random_seed_max: int = Field(
        ge=1,
        validation_alias="WEREWOLF_STREAMLIT_RANDOM_SEED_MAX",
    )
    streamlit_service_name: str = Field(
        validation_alias="WEREWOLF_STREAMLIT_SERVICE_NAME",
    )
