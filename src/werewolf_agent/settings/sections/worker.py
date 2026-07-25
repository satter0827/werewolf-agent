"""worker runtime settings section."""

from __future__ import annotations

from pydantic import BaseModel, Field

from werewolf_agent.settings.constants import (
    MIN_INTERVAL_SECONDS,
    MIN_TIMEOUT_SECONDS_EXCLUSIVE,
)
from werewolf_agent.settings.defaults import (
    DEFAULT_ADVANCE_JOB_POLL_INTERVAL_SECONDS,
    DEFAULT_ADVANCE_JOB_POLL_TIMEOUT_SECONDS,
    DEFAULT_SUPABASE_WORKER_BATCH_SIZE,
    DEFAULT_SUPABASE_WORKER_CLAIM_SECONDS,
    DEFAULT_SUPABASE_WORKER_ID,
    DEFAULT_SUPABASE_WORKER_POLL_INTERVAL_SECONDS,
    DEFAULT_WORKER_PAID_LLM_BASE_URL,
    DEFAULT_WORKER_PAID_LLM_MODEL,
    DEFAULT_WORKER_PAID_LLM_PROVIDER,
)


class WorkerSettings(BaseModel):
    """Settings owned by the worker runtime boundary."""

    worker_paid_llm_provider: str = Field(
        default=DEFAULT_WORKER_PAID_LLM_PROVIDER,
        validation_alias="WEREWOLF_WORKER_PAID_LLM_PROVIDER",
    )
    worker_paid_llm_model: str = Field(
        default=DEFAULT_WORKER_PAID_LLM_MODEL,
        validation_alias="WEREWOLF_WORKER_PAID_LLM_MODEL",
    )
    worker_paid_llm_base_url: str = Field(
        default=DEFAULT_WORKER_PAID_LLM_BASE_URL,
        validation_alias="WEREWOLF_WORKER_PAID_LLM_BASE_URL",
    )
    supabase_worker_id: str = Field(
        default=DEFAULT_SUPABASE_WORKER_ID,
        validation_alias="WEREWOLF_SUPABASE_WORKER_ID",
    )
    supabase_worker_poll_interval_seconds: float = Field(
        default=DEFAULT_SUPABASE_WORKER_POLL_INTERVAL_SECONDS,
        ge=MIN_INTERVAL_SECONDS,
        validation_alias="WEREWOLF_SUPABASE_WORKER_POLL_INTERVAL_SECONDS",
    )
    supabase_worker_batch_size: int = Field(
        default=DEFAULT_SUPABASE_WORKER_BATCH_SIZE,
        ge=1,
        validation_alias="WEREWOLF_SUPABASE_WORKER_BATCH_SIZE",
    )
    supabase_worker_claim_seconds: int = Field(
        default=DEFAULT_SUPABASE_WORKER_CLAIM_SECONDS,
        ge=1,
        validation_alias="WEREWOLF_SUPABASE_WORKER_CLAIM_SECONDS",
    )
    advance_job_poll_interval_seconds: float = Field(
        default=DEFAULT_ADVANCE_JOB_POLL_INTERVAL_SECONDS,
        ge=MIN_INTERVAL_SECONDS,
        validation_alias="WEREWOLF_ADVANCE_JOB_POLL_INTERVAL_SECONDS",
    )
    advance_job_poll_timeout_seconds: float = Field(
        default=DEFAULT_ADVANCE_JOB_POLL_TIMEOUT_SECONDS,
        gt=MIN_TIMEOUT_SECONDS_EXCLUSIVE,
        validation_alias="WEREWOLF_ADVANCE_JOB_POLL_TIMEOUT_SECONDS",
    )
