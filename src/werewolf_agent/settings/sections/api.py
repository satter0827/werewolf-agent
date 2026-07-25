"""api runtime settings section."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field

from werewolf_agent.settings.constants import (
    MIN_PAGE_LIMIT,
    MIN_TEXT_MAX_CHARS,
)
from werewolf_agent.settings.defaults import (
    DEFAULT_API_BASE_URL,
    DEFAULT_API_CONFIG_REVISION,
    DEFAULT_API_CONTRACT_VERSION,
    DEFAULT_API_CORS_ORIGINS,
    DEFAULT_API_DOCS_ENABLED,
    DEFAULT_API_GAME_LIST_DEFAULT_LIMIT,
    DEFAULT_API_GAME_LIST_MAX_LIMIT,
    DEFAULT_API_HOST,
    DEFAULT_API_MAX_BODY_BYTES,
    DEFAULT_API_MAX_CONCURRENT_REQUESTS,
    DEFAULT_API_MESSAGE_MAX_CHARS,
    DEFAULT_API_PORT,
    DEFAULT_API_RATE_LIMIT_REQUESTS,
    DEFAULT_API_RATE_LIMIT_WINDOW_SECONDS,
    DEFAULT_API_TIMELINE_DEFAULT_LIMIT,
    DEFAULT_API_TIMELINE_MAX_LIMIT,
    DEFAULT_API_TIMEOUT_SECONDS,
    DEFAULT_REVEAL_API_ENABLED,
    DEFAULT_UI_DEFAULT_MANUAL_PLAYER_ID,
    DEFAULT_UI_DEFAULT_SETUP_SEED,
    DEFAULT_UI_DESKTOP_BREAKPOINT,
    DEFAULT_UI_MOTION,
    DEFAULT_UI_OPERATION_POLL_INTERVAL_MS,
    DEFAULT_UI_OPERATION_POLL_TIMEOUT_MS,
    DEFAULT_UI_SPACING_UNIT,
    DEFAULT_UI_THEME_ID,
    UiMotion,
)


class ApiSettings(BaseModel):
    """Settings owned by the api runtime boundary."""

    reveal_api_enabled: bool = Field(
        default=DEFAULT_REVEAL_API_ENABLED,
        validation_alias="WEREWOLF_REVEAL_API_ENABLED",
    )
    api_game_list_default_limit: int = Field(
        default=DEFAULT_API_GAME_LIST_DEFAULT_LIMIT,
        ge=MIN_PAGE_LIMIT,
        validation_alias="WEREWOLF_API_GAME_LIST_DEFAULT_LIMIT",
    )
    api_game_list_max_limit: int = Field(
        default=DEFAULT_API_GAME_LIST_MAX_LIMIT,
        ge=MIN_PAGE_LIMIT,
        validation_alias="WEREWOLF_API_GAME_LIST_MAX_LIMIT",
    )
    api_timeline_default_limit: int = Field(
        default=DEFAULT_API_TIMELINE_DEFAULT_LIMIT,
        ge=MIN_PAGE_LIMIT,
        validation_alias="WEREWOLF_API_TIMELINE_DEFAULT_LIMIT",
    )
    api_timeline_max_limit: int = Field(
        default=DEFAULT_API_TIMELINE_MAX_LIMIT,
        ge=MIN_PAGE_LIMIT,
        validation_alias="WEREWOLF_API_TIMELINE_MAX_LIMIT",
    )
    api_host: str = Field(
        default=DEFAULT_API_HOST,
        validation_alias="WEREWOLF_API_HOST",
    )
    api_port: int = Field(
        default=DEFAULT_API_PORT,
        ge=1,
        le=65535,
        validation_alias="WEREWOLF_API_PORT",
    )
    api_base_url: str = Field(
        default=DEFAULT_API_BASE_URL,
        validation_alias="WEREWOLF_API_BASE_URL",
    )
    api_contract_version: str = Field(
        default=DEFAULT_API_CONTRACT_VERSION,
        validation_alias="WEREWOLF_API_CONTRACT_VERSION",
    )
    api_config_revision: str = Field(
        default=DEFAULT_API_CONFIG_REVISION,
        validation_alias="WEREWOLF_API_CONFIG_REVISION",
    )
    api_docs_enabled: bool = Field(
        default=DEFAULT_API_DOCS_ENABLED,
        validation_alias="WEREWOLF_API_DOCS_ENABLED",
    )
    api_cors_origins: str = Field(
        default=DEFAULT_API_CORS_ORIGINS,
        validation_alias="WEREWOLF_API_CORS_ORIGINS",
    )
    api_max_body_bytes: int = Field(
        default=DEFAULT_API_MAX_BODY_BYTES,
        ge=1024,
        validation_alias="WEREWOLF_API_MAX_BODY_BYTES",
    )
    api_message_max_chars: int = Field(
        default=DEFAULT_API_MESSAGE_MAX_CHARS,
        ge=MIN_TEXT_MAX_CHARS,
        validation_alias="WEREWOLF_API_MESSAGE_MAX_CHARS",
    )
    api_rate_limit_requests: int = Field(
        default=DEFAULT_API_RATE_LIMIT_REQUESTS,
        ge=1,
        validation_alias="WEREWOLF_API_RATE_LIMIT_REQUESTS",
    )
    api_rate_limit_window_seconds: int = Field(
        default=DEFAULT_API_RATE_LIMIT_WINDOW_SECONDS,
        ge=1,
        validation_alias="WEREWOLF_API_RATE_LIMIT_WINDOW_SECONDS",
    )
    api_timeout_seconds: float = Field(
        default=DEFAULT_API_TIMEOUT_SECONDS,
        gt=0,
        validation_alias="WEREWOLF_API_TIMEOUT_SECONDS",
    )
    api_max_concurrent_requests: int = Field(
        default=DEFAULT_API_MAX_CONCURRENT_REQUESTS,
        ge=1,
        validation_alias="WEREWOLF_API_MAX_CONCURRENT_REQUESTS",
    )
    ui_theme_id: str = Field(
        default=DEFAULT_UI_THEME_ID,
        min_length=1,
        validation_alias="WEREWOLF_UI_THEME_ID",
    )
    ui_spacing_unit: int = Field(
        default=DEFAULT_UI_SPACING_UNIT,
        ge=1,
        le=16,
        validation_alias="WEREWOLF_UI_SPACING_UNIT",
    )
    ui_desktop_breakpoint: int = Field(
        default=DEFAULT_UI_DESKTOP_BREAKPOINT,
        ge=640,
        le=1920,
        validation_alias="WEREWOLF_UI_DESKTOP_BREAKPOINT",
    )
    ui_motion: UiMotion = Field(
        default=cast(UiMotion, DEFAULT_UI_MOTION),
        validation_alias="WEREWOLF_UI_MOTION",
    )
    ui_default_manual_player_id: str = Field(
        default=DEFAULT_UI_DEFAULT_MANUAL_PLAYER_ID,
        min_length=1,
        validation_alias="WEREWOLF_UI_DEFAULT_MANUAL_PLAYER_ID",
    )
    ui_default_setup_seed: str = Field(
        default=DEFAULT_UI_DEFAULT_SETUP_SEED,
        min_length=1,
        validation_alias="WEREWOLF_UI_DEFAULT_SETUP_SEED",
    )
    ui_operation_poll_interval_ms: int = Field(
        default=DEFAULT_UI_OPERATION_POLL_INTERVAL_MS,
        ge=50,
        le=10_000,
        validation_alias="WEREWOLF_UI_OPERATION_POLL_INTERVAL_MS",
    )
    ui_operation_poll_timeout_ms: int = Field(
        default=DEFAULT_UI_OPERATION_POLL_TIMEOUT_MS,
        ge=1_000,
        le=600_000,
        validation_alias="WEREWOLF_UI_OPERATION_POLL_TIMEOUT_MS",
    )
