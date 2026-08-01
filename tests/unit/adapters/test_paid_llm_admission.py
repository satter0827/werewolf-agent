"""有料LLM admission制御の単体契約。"""

from __future__ import annotations

from uuid import UUID

import pytest

from werewolf_agent.adapters.supabase.paid_llm_admission import (
    PaidLlmAdmission,
    SupabasePaidLlmAdmissionGate,
)
from werewolf_agent.application.errors import AppError
from werewolf_agent.contracts.errors import ErrorCode

ADMISSION_ID = UUID("00000000-0000-0000-0000-000000000001")


class _Cursor:
    def __init__(self, row: object) -> None:
        self._row = row

    def fetchone(self) -> object:
        return self._row


class _Connection:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, object]] = []

    def execute(self, sql: str, parameters: object = None) -> _Cursor:
        self.calls.append((sql, parameters))
        return _Cursor(self.rows.pop(0))


def _reserve(connection: _Connection) -> PaidLlmAdmission:
    return SupabasePaidLlmAdmissionGate(connection).reserve(
        operation_id="operation-1",
        actor_user_id="user-1",
        worker_id="worker-1",
        daily_limit=3,
        concurrency_limit=2,
        ttl_seconds=300,
    )


def test_reserve_serializes_checks_and_inserts_one_durable_admission() -> None:
    connection = _Connection([None, None, None, (1,), (0,), (ADMISSION_ID,)])

    admission = _reserve(connection)

    assert admission == PaidLlmAdmission(str(ADMISSION_ID))
    assert "pg_advisory_xact_lock" in connection.calls[0][0]
    assert "status = 'expired'" in connection.calls[1][0]
    assert "date_trunc('day'" in connection.calls[3][0]
    assert "status = 'active'" in connection.calls[4][0]
    assert connection.calls[5][1] == (
        "operation-1",
        "user-1",
        "worker-1",
        300,
    )


@pytest.mark.parametrize(
    ("rows", "code", "retryable", "message"),
    [
        ([None, None, ("failed",)], ErrorCode.LLM_PROVIDER_UNAVAILABLE, False, "already"),
        ([None, None, None, (3,)], ErrorCode.LLM_PROVIDER_UNAVAILABLE, False, "daily"),
        (
            [None, None, None, (0,), (2,)],
            ErrorCode.REQUEST_CONCURRENCY_LIMITED,
            True,
            "capacity",
        ),
    ],
)
def test_reserve_fails_closed_before_insert(
    rows: list[object],
    code: ErrorCode,
    retryable: bool,
    message: str,
) -> None:
    connection = _Connection(rows)

    with pytest.raises(AppError, match=message) as captured:
        _reserve(connection)

    assert captured.value.code is code
    assert captured.value.retryable is retryable
    assert all("insert into" not in sql.casefold() for sql, _ in connection.calls)


def test_finish_releases_concurrency_without_deleting_budget_history() -> None:
    connection = _Connection([(ADMISSION_ID,)])

    SupabasePaidLlmAdmissionGate(connection).finish(
        PaidLlmAdmission(str(ADMISSION_ID)),
        outcome="completed",
    )

    sql, parameters = connection.calls[0]
    assert "update private.paid_llm_admissions" in sql
    assert "delete" not in sql.casefold()
    assert parameters == ("completed", str(ADMISSION_ID))


def test_finish_rejects_expired_or_released_admission() -> None:
    connection = _Connection([None])

    with pytest.raises(AppError, match="no longer active") as captured:
        SupabasePaidLlmAdmissionGate(connection).finish(
            PaidLlmAdmission(str(ADMISSION_ID)),
            outcome="failed",
        )

    assert captured.value.retryable is False


@pytest.mark.parametrize(("row", "expected"), [((ADMISSION_ID,), True), (None, False)])
def test_renew_only_extends_an_unexpired_active_admission(
    row: object,
    expected: bool,
) -> None:
    connection = _Connection([row])

    renewed = SupabasePaidLlmAdmissionGate(connection).renew(
        PaidLlmAdmission(str(ADMISSION_ID)),
        ttl_seconds=300,
    )

    assert renewed is expected
    assert connection.calls[0][1] == (300, str(ADMISSION_ID))
