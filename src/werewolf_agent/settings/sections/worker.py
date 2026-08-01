"""worker runtime settings section."""

from __future__ import annotations

from pydantic import BaseModel, Field

from werewolf_agent.settings.constants import (
    MIN_INTERVAL_SECONDS,
    MIN_TIMEOUT_SECONDS_EXCLUSIVE,
)


class WorkerSettings(BaseModel):
    """Settings owned by the worker runtime boundary."""

    worker_paid_llm_provider: str = Field(
        validation_alias="WEREWOLF_WORKER_PAID_LLM_PROVIDER",
    )
    worker_paid_llm_model: str = Field(
        validation_alias="WEREWOLF_WORKER_PAID_LLM_MODEL",
    )
    worker_paid_llm_base_url: str = Field(
        validation_alias="WEREWOLF_WORKER_PAID_LLM_BASE_URL",
    )
    worker_paid_llm_enabled: bool = Field(
        validation_alias="WEREWOLF_WORKER_PAID_LLM_ENABLED",
    )
    worker_paid_llm_daily_advance_limit: int = Field(
        ge=1,
        validation_alias="WEREWOLF_WORKER_PAID_LLM_DAILY_ADVANCE_LIMIT",
    )
    worker_paid_llm_max_concurrent_advances: int = Field(
        ge=1,
        validation_alias="WEREWOLF_WORKER_PAID_LLM_MAX_CONCURRENT_ADVANCES",
    )
    worker_paid_llm_admission_ttl_seconds: int = Field(
        ge=1,
        validation_alias="WEREWOLF_WORKER_PAID_LLM_ADMISSION_TTL_SECONDS",
    )
    supabase_worker_id: str = Field(
        validation_alias="WEREWOLF_SUPABASE_WORKER_ID",
    )
    supabase_worker_poll_interval_seconds: float = Field(
        ge=MIN_INTERVAL_SECONDS,
        validation_alias="WEREWOLF_SUPABASE_WORKER_POLL_INTERVAL_SECONDS",
    )
    supabase_worker_batch_size: int = Field(
        ge=1,
        le=5,
        validation_alias="WEREWOLF_SUPABASE_WORKER_BATCH_SIZE",
    )
    supabase_worker_claim_seconds: int = Field(
        ge=1,
        validation_alias="WEREWOLF_SUPABASE_WORKER_CLAIM_SECONDS",
    )
    supabase_worker_pool_min_size: int = Field(
        ge=1,
        validation_alias="WEREWOLF_SUPABASE_WORKER_POOL_MIN_SIZE",
    )
    supabase_worker_pool_max_size: int = Field(
        ge=1,
        validation_alias="WEREWOLF_SUPABASE_WORKER_POOL_MAX_SIZE",
    )
    supabase_worker_heartbeat_seconds: int = Field(
        ge=1,
        validation_alias="WEREWOLF_SUPABASE_WORKER_HEARTBEAT_SECONDS",
    )
    supabase_worker_max_attempts: int = Field(
        ge=1,
        validation_alias="WEREWOLF_SUPABASE_WORKER_MAX_ATTEMPTS",
    )
    advance_job_poll_interval_seconds: float = Field(
        ge=MIN_INTERVAL_SECONDS,
        validation_alias="WEREWOLF_ADVANCE_JOB_POLL_INTERVAL_SECONDS",
    )
    advance_job_poll_timeout_seconds: float = Field(
        gt=MIN_TIMEOUT_SECONDS_EXCLUSIVE,
        validation_alias="WEREWOLF_ADVANCE_JOB_POLL_TIMEOUT_SECONDS",
    )
