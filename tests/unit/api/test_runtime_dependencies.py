"""Fault isolation for API process-owned dependencies."""

from typing import Any, cast

import pytest

from werewolf_agent.api.dependencies import RequestServices
from werewolf_agent.api.runtime import AvailabilityGuardedOperationQueue, RuntimeDependencies
from werewolf_agent.contracts import AppError, ErrorCode


class _Pool:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_request_services_disable_reveal_by_default() -> None:
    """組み立て漏れでも完全状態を公開しない。"""
    services = RequestServices(
        games=cast(Any, object()),
        setups=cast(Any, object()),
        message_max_chars=100,
    )

    assert services.reveal_api_enabled is False


def test_database_open_failure_degrades_status_without_raising() -> None:
    pool = _Pool()

    def fail_open(_pool: object, _timeout: float) -> None:
        raise AppError("database unavailable", code=ErrorCode.API_UNAVAILABLE)

    dependencies = RuntimeDependencies(
        pool=pool,
        authentication_configured=True,
        database_configured=True,
        open_pool=fail_open,
    )

    dependencies.open(timeout=1.0)
    status = dependencies.public_status()

    assert status.status == "degraded"
    assert {item.component: item.status for item in status.components} == {
        "api": "available",
        "authentication": "available",
        "database": "unavailable",
        "operation_queue": "unavailable",
    }
    dependencies.close()
    assert pool.closed is True


def test_queue_probe_failure_only_degrades_operation_queue() -> None:
    pool = _Pool()

    def open_ok(_pool: object, _timeout: float) -> None:
        return None

    def fail_queue(_pool: object) -> None:
        raise AppError("queue unavailable", code=ErrorCode.API_UNAVAILABLE)

    dependencies = RuntimeDependencies(
        pool=pool,
        authentication_configured=True,
        database_configured=True,
        open_pool=open_ok,
        probe_operation_queue=fail_queue,
    )

    dependencies.open(timeout=1.0)
    status = dependencies.public_status()

    assert status.status == "degraded"
    assert {item.component: item.status for item in status.components} == {
        "api": "available",
        "authentication": "available",
        "database": "available",
        "operation_queue": "unavailable",
    }


def test_unavailable_queue_rejects_mutation_but_keeps_reads() -> None:
    class Queue:
        def enqueue(self, **_kwargs: object) -> None:
            raise AssertionError("unavailable queue must not enqueue")

        def get(self, operation_id: str, *, owner_user_id: str) -> str:
            return f"{operation_id}:{owner_user_id}"

    queue = AvailabilityGuardedOperationQueue(cast(Any, Queue()), available=lambda: False)

    assert queue.get("operation-1", owner_user_id="owner-1") == "operation-1:owner-1"
    with pytest.raises(AppError, match="処理キュー"):
        queue.enqueue(
            operation_type="advance",
            owner_user_id="owner-1",
            idempotency_key="key-1",
            request_payload={},
            llm_mode=None,
        )
