"""database runtime settings section."""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr

from werewolf_agent.settings.constants import (
    MIN_TIMEOUT_SECONDS_EXCLUSIVE,
)


class DatabaseSettings(BaseModel):
    """Settings owned by the database runtime boundary."""

    supabase_url: str = Field(
        validation_alias="WEREWOLF_SUPABASE_URL",
    )
    supabase_publishable_key: SecretStr = Field(
        validation_alias="WEREWOLF_SUPABASE_PUBLISHABLE_KEY",
    )
    supabase_db_dsn: SecretStr = Field(
        validation_alias="WEREWOLF_SUPABASE_DB_DSN",
    )
    supabase_auth_timeout_seconds: float = Field(
        gt=MIN_TIMEOUT_SECONDS_EXCLUSIVE,
        validation_alias="WEREWOLF_SUPABASE_AUTH_TIMEOUT_SECONDS",
    )
    supabase_rest_timeout_seconds: float = Field(
        gt=MIN_TIMEOUT_SECONDS_EXCLUSIVE,
        validation_alias="WEREWOLF_SUPABASE_REST_TIMEOUT_SECONDS",
    )
    supabase_api_pool_min_size: int = Field(
        ge=1,
        validation_alias="WEREWOLF_SUPABASE_API_POOL_MIN_SIZE",
    )
    supabase_api_pool_max_size: int = Field(
        ge=1,
        validation_alias="WEREWOLF_SUPABASE_API_POOL_MAX_SIZE",
    )
    supabase_pool_timeout_seconds: float = Field(
        gt=MIN_TIMEOUT_SECONDS_EXCLUSIVE,
        validation_alias="WEREWOLF_SUPABASE_POOL_TIMEOUT_SECONDS",
    )
    supabase_jwt_audience: str = Field(
        validation_alias="WEREWOLF_SUPABASE_JWT_AUDIENCE",
    )
    supabase_jwt_issuer: str = Field(
        validation_alias="WEREWOLF_SUPABASE_JWT_ISSUER",
    )
    supabase_jwks_url: str = Field(
        validation_alias="WEREWOLF_SUPABASE_JWKS_URL",
    )
