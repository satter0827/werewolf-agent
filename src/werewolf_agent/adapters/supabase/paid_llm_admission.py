"""Database-backed admission control for paid LLM advances."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from werewolf_agent.application.errors import AppError
from werewolf_agent.contracts.errors import ErrorCode

ADMISSION_LOCK_KEY = "werewolf-agent:paid-llm-admission"
AdmissionOutcome = Literal["completed", "failed"]


@dataclass(frozen=True, slots=True)
class PaidLlmAdmission:
    """One durable concurrency reservation for a paid advance operation."""

    admission_id: str


class SupabasePaidLlmAdmissionGate:
    """Atomically enforce paid-operation budget and shared concurrency limits."""

    def __init__(self, connection: Any) -> None:
        """Bind admission operations to one transaction-owned connection."""
        self._connection = connection

    def reserve(
        self,
        *,
        operation_id: str,
        actor_user_id: str,
        worker_id: str,
        daily_limit: int,
        concurrency_limit: int,
        ttl_seconds: int,
    ) -> PaidLlmAdmission:
        """Reserve capacity or fail before any paid provider call can start."""
        self._connection.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (ADMISSION_LOCK_KEY,),
        )
        self._connection.execute(
            """
            update private.paid_llm_admissions
            set status = 'expired', released_at = now()
            where status = 'active' and expires_at <= now()
            """
        )
        existing = self._connection.execute(
            """
            select status from private.paid_llm_admissions
            where operation_id = %s
            """,
            (operation_id,),
        ).fetchone()
        if existing is not None:
            raise AppError(
                "This paid LLM operation already has an admission record.",
                code=ErrorCode.LLM_PROVIDER_UNAVAILABLE,
                retryable=False,
            )
        daily_count = self._connection.execute(
            """
            select count(*)
            from private.paid_llm_admissions
            where actor_user_id = %s
              and reserved_at >= (
                date_trunc('day', now() at time zone 'UTC') at time zone 'UTC'
              )
            """,
            (actor_user_id,),
        ).fetchone()
        if daily_count is None or int(daily_count[0]) >= daily_limit:
            raise AppError(
                "The daily paid LLM operation limit has been reached.",
                code=ErrorCode.LLM_PROVIDER_UNAVAILABLE,
                retryable=False,
            )
        active_count = self._connection.execute(
            """
            select count(*) from private.paid_llm_admissions
            where status = 'active' and expires_at > now()
            """
        ).fetchone()
        if active_count is None or int(active_count[0]) >= concurrency_limit:
            raise AppError(
                "Paid LLM capacity is temporarily full.",
                code=ErrorCode.REQUEST_CONCURRENCY_LIMITED,
                retryable=True,
            )
        row = self._connection.execute(
            """
            insert into private.paid_llm_admissions (
              operation_id, actor_user_id, worker_id, expires_at
            ) values (%s, %s, %s, now() + (%s * interval '1 second'))
            returning admission_id
            """,
            (operation_id, actor_user_id, worker_id, ttl_seconds),
        ).fetchone()
        if row is None:
            raise AppError(
                "Paid LLM capacity could not be reserved.",
                code=ErrorCode.LLM_PROVIDER_UNAVAILABLE,
                retryable=False,
            )
        return PaidLlmAdmission(admission_id=str(row[0]))

    def finish(self, admission: PaidLlmAdmission, *, outcome: AdmissionOutcome) -> None:
        """Release shared capacity while retaining the consumed daily budget record."""
        row = self._connection.execute(
            """
            update private.paid_llm_admissions
            set status = %s, released_at = now()
            where admission_id = %s and status = 'active'
            returning admission_id
            """,
            (outcome, admission.admission_id),
        ).fetchone()
        if row is None:
            raise AppError(
                "The paid LLM capacity reservation is no longer active.",
                code=ErrorCode.LLM_PROVIDER_UNAVAILABLE,
                retryable=False,
            )

    def renew(self, admission: PaidLlmAdmission, *, ttl_seconds: int) -> bool:
        """Extend one active reservation while its worker lease remains healthy."""
        row = self._connection.execute(
            """
            update private.paid_llm_admissions
            set expires_at = now() + (%s * interval '1 second')
            where admission_id = %s and status = 'active' and expires_at > now()
            returning admission_id
            """,
            (ttl_seconds, admission.admission_id),
        ).fetchone()
        return row is not None


__all__ = ["PaidLlmAdmission", "SupabasePaidLlmAdmissionGate"]
