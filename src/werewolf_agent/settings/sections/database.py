"""database runtime settings section."""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr

from werewolf_agent.settings.constants import (
    MIN_TIMEOUT_SECONDS_EXCLUSIVE,
)
from werewolf_agent.settings.defaults import (
    DEFAULT_SUPABASE_AUTH_TIMEOUT_SECONDS,
    DEFAULT_SUPABASE_DB_DSN,
    DEFAULT_SUPABASE_JWKS_URL,
    DEFAULT_SUPABASE_JWT_AUDIENCE,
    DEFAULT_SUPABASE_JWT_ISSUER,
    DEFAULT_SUPABASE_PUBLISHABLE_KEY,
    DEFAULT_SUPABASE_REST_TIMEOUT_SECONDS,
    DEFAULT_SUPABASE_URL,
)


class DatabaseSettings(BaseModel):
    """Settings owned by the database runtime boundary."""

    supabase_url: str = Field(
        default=DEFAULT_SUPABASE_URL,
        validation_alias="WEREWOLF_SUPABASE_URL",
    )
    supabase_publishable_key: SecretStr = Field(
        default=SecretStr(DEFAULT_SUPABASE_PUBLISHABLE_KEY),
        validation_alias="WEREWOLF_SUPABASE_PUBLISHABLE_KEY",
    )
    supabase_db_dsn: SecretStr = Field(
        default=SecretStr(DEFAULT_SUPABASE_DB_DSN),
        validation_alias="WEREWOLF_SUPABASE_DB_DSN",
    )
    supabase_auth_timeout_seconds: float = Field(
        default=DEFAULT_SUPABASE_AUTH_TIMEOUT_SECONDS,
        gt=MIN_TIMEOUT_SECONDS_EXCLUSIVE,
        validation_alias="WEREWOLF_SUPABASE_AUTH_TIMEOUT_SECONDS",
    )
    supabase_rest_timeout_seconds: float = Field(
        default=DEFAULT_SUPABASE_REST_TIMEOUT_SECONDS,
        gt=MIN_TIMEOUT_SECONDS_EXCLUSIVE,
        validation_alias="WEREWOLF_SUPABASE_REST_TIMEOUT_SECONDS",
    )
    supabase_jwt_audience: str = Field(
        default=DEFAULT_SUPABASE_JWT_AUDIENCE,
        validation_alias="WEREWOLF_SUPABASE_JWT_AUDIENCE",
    )
    supabase_jwt_issuer: str = Field(
        default=DEFAULT_SUPABASE_JWT_ISSUER,
        validation_alias="WEREWOLF_SUPABASE_JWT_ISSUER",
    )
    supabase_jwks_url: str = Field(
        default=DEFAULT_SUPABASE_JWKS_URL,
        validation_alias="WEREWOLF_SUPABASE_JWKS_URL",
    )
