from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from werewolf_agent.adapters.supabase.operations import SupabaseOperationQueue
from werewolf_agent.contracts import AppError, ErrorCode


class _Result:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self._row


class _Connection:
    def __init__(self, *, stored_hash: str | None = None) -> None:
        self.stored_hash = stored_hash
        self.parameters: tuple[Any, ...] = ()
        self.inserted_llm_mode = ""

    def execute(self, query: str, parameters: tuple[Any, ...]) -> _Result:
        if "select llm_mode" in query:
            return _Result({"llm_mode": "fake"})
        self.parameters = parameters
        self.inserted_llm_mode = str(parameters[7])
        request_hash = self.stored_hash or str(parameters[-1])
        now = datetime.now(UTC)
        return _Result(
            {
                "request_id": "operation-1",
                "operation_type": parameters[0],
                "owner_user_id": parameters[1],
                "game_id": parameters[4],
                "expected_version": parameters[6],
                "request_hash": request_hash,
                "status": "queued",
                "created_at": now,
                "updated_at": now,
            }
        )


def test_enqueue_persists_a_stable_request_hash() -> None:
    connection = _Connection()
    queue = SupabaseOperationQueue(connection)

    operation = queue.enqueue(
        operation_type="advance",
        owner_user_id="user-1",
        idempotency_key="request-1",
        request_payload={"reason": "next"},
        llm_mode=None,
        game_id="game-1",
        expected_version=2,
    )

    assert operation.operation_id == "operation-1"
    assert isinstance(connection.parameters[-1], str)
    assert len(connection.parameters[-1]) == 64
    assert connection.inserted_llm_mode == "fake"


def test_enqueue_rejects_key_reuse_for_a_different_request() -> None:
    connection = _Connection(stored_hash="0" * 64)
    queue = SupabaseOperationQueue(connection)

    with pytest.raises(AppError) as exc_info:
        queue.enqueue(
            operation_type="advance",
            owner_user_id="user-1",
            idempotency_key="request-1",
            request_payload={},
            llm_mode=None,
            game_id="game-1",
            expected_version=2,
        )

    assert exc_info.value.code == ErrorCode.REQUEST_IDEMPOTENCY_CONFLICT


def test_existing_game_mode_does_not_depend_on_the_current_principal_mode() -> None:
    connection = _Connection()
    queue = SupabaseOperationQueue(connection)

    queue.enqueue(
        operation_type="advance",
        owner_user_id="user-1",
        idempotency_key="request-1",
        request_payload={},
        llm_mode="paid",
        game_id="game-1",
        expected_version=2,
    )

    assert connection.inserted_llm_mode == "fake"
