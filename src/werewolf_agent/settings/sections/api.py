"""api runtime settings section."""

from __future__ import annotations

from pydantic import BaseModel, Field

from werewolf_agent.settings.constants import (
    MIN_PAGE_LIMIT,
    MIN_TEXT_MAX_CHARS,
)
from werewolf_agent.settings.defaults import (
    UiMotion,
)


class ApiSettings(BaseModel):
    """Settings owned by the api runtime boundary."""

    reveal_api_enabled: bool = Field(
        validation_alias="WEREWOLF_REVEAL_API_ENABLED",
    )
    api_game_list_default_limit: int = Field(
        ge=MIN_PAGE_LIMIT,
        validation_alias="WEREWOLF_API_GAME_LIST_DEFAULT_LIMIT",
    )
    api_game_list_max_limit: int = Field(
        ge=MIN_PAGE_LIMIT,
        validation_alias="WEREWOLF_API_GAME_LIST_MAX_LIMIT",
    )
    api_timeline_default_limit: int = Field(
        ge=MIN_PAGE_LIMIT,
        validation_alias="WEREWOLF_API_TIMELINE_DEFAULT_LIMIT",
    )
    api_timeline_max_limit: int = Field(
        ge=MIN_PAGE_LIMIT,
        validation_alias="WEREWOLF_API_TIMELINE_MAX_LIMIT",
    )
    api_host: str = Field(
        validation_alias="WEREWOLF_API_HOST",
    )
    api_port: int = Field(
        ge=1,
        le=65535,
        validation_alias="WEREWOLF_API_PORT",
    )
    api_base_url: str = Field(
        validation_alias="WEREWOLF_API_BASE_URL",
    )
    api_contract_version: str = Field(
        validation_alias="WEREWOLF_API_CONTRACT_VERSION",
    )
    api_config_revision: str = Field(
        validation_alias="WEREWOLF_API_CONFIG_REVISION",
    )
    api_instance_id: str = Field(
        validation_alias="WEREWOLF_API_INSTANCE_ID",
    )
    api_docs_enabled: bool = Field(
        validation_alias="WEREWOLF_API_DOCS_ENABLED",
    )
    api_cors_origins: str = Field(
        validation_alias="WEREWOLF_API_CORS_ORIGINS",
    )
    api_max_body_bytes: int = Field(
        ge=1024,
        validation_alias="WEREWOLF_API_MAX_BODY_BYTES",
    )
    api_message_max_chars: int = Field(
        ge=MIN_TEXT_MAX_CHARS,
        validation_alias="WEREWOLF_API_MESSAGE_MAX_CHARS",
    )
    api_rate_limit_requests: int = Field(
        ge=1,
        validation_alias="WEREWOLF_API_RATE_LIMIT_REQUESTS",
    )
    api_rate_limit_window_seconds: int = Field(
        ge=1,
        validation_alias="WEREWOLF_API_RATE_LIMIT_WINDOW_SECONDS",
    )
    api_timeout_seconds: float = Field(
        gt=0,
        validation_alias="WEREWOLF_API_TIMEOUT_SECONDS",
    )
    api_max_concurrent_requests: int = Field(
        ge=1,
        validation_alias="WEREWOLF_API_MAX_CONCURRENT_REQUESTS",
    )
    ui_theme_id: str = Field(
        min_length=1,
        validation_alias="WEREWOLF_UI_THEME_ID",
    )
    ui_spacing_unit: int = Field(
        ge=1,
        le=16,
        validation_alias="WEREWOLF_UI_SPACING_UNIT",
    )
    ui_desktop_breakpoint: int = Field(
        ge=640,
        le=1920,
        validation_alias="WEREWOLF_UI_DESKTOP_BREAKPOINT",
    )
    ui_motion: UiMotion = Field(
        validation_alias="WEREWOLF_UI_MOTION",
    )
    ui_default_manual_player_id: str = Field(
        min_length=1,
        validation_alias="WEREWOLF_UI_DEFAULT_MANUAL_PLAYER_ID",
    )
    ui_default_setup_seed: str = Field(
        min_length=1,
        validation_alias="WEREWOLF_UI_DEFAULT_SETUP_SEED",
    )
    ui_operation_poll_interval_ms: int = Field(
        ge=50,
        le=10_000,
        validation_alias="WEREWOLF_UI_OPERATION_POLL_INTERVAL_MS",
    )
    ui_operation_poll_timeout_ms: int = Field(
        ge=1_000,
        le=600_000,
        validation_alias="WEREWOLF_UI_OPERATION_POLL_TIMEOUT_MS",
    )
