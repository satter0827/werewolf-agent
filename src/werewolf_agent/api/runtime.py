"""Process-owned dependency availability for the API boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from werewolf_agent.application import OperationQueue, QueuedOperation
from werewolf_agent.contracts import AppError, ErrorCode
from werewolf_agent.contracts.api import (
    RuntimeAvailability,
    RuntimeComponentStatus,
    RuntimeStatusResponse,
)


@dataclass
class RuntimeDependencies:
    """Keep optional infrastructure state outside application services."""

    pool: Any | None
    authentication_configured: bool
    database_configured: bool
    open_pool: Callable[[Any, float], None]
    probe_database: Callable[[Any], None] | None = None
    probe_operation_queue: Callable[[Any], None] | None = None
    database_available: bool = False
    database_reason_code: str | None = None
    operation_queue_available: bool = False
    operation_queue_reason_code: str | None = None

    def open(self, *, timeout: float) -> None:
        """Open the database when configured without failing API liveness."""
        if self.pool is None:
            self.database_reason_code = "database_not_configured"
            self.operation_queue_reason_code = "operation_queue_unavailable"
            return
        try:
            self.open_pool(self.pool, timeout)
        except AppError:
            self.database_available = False
            self.database_reason_code = "database_unavailable"
            self.operation_queue_available = False
            self.operation_queue_reason_code = "operation_queue_unavailable"
            return
        self.database_available = True
        self.database_reason_code = None
        self._refresh_operation_queue()

    def refresh(self) -> None:
        """Refresh dynamic dependency state without changing external resources."""
        if self.pool is None:
            self.database_available = False
            self.database_reason_code = "database_not_configured"
            self.operation_queue_available = False
            self.operation_queue_reason_code = "operation_queue_unavailable"
            return
        if self.probe_database is None:
            if self.database_available:
                self._refresh_operation_queue()
            return
        try:
            self.probe_database(self.pool)
        except Exception:
            self.database_available = False
            self.database_reason_code = "database_unavailable"
            self.operation_queue_available = False
            self.operation_queue_reason_code = "operation_queue_unavailable"
            return
        self.database_available = True
        self.database_reason_code = None
        self._refresh_operation_queue()

    def _refresh_operation_queue(self) -> None:
        if self.probe_operation_queue is None:
            self.operation_queue_available = True
            self.operation_queue_reason_code = None
            return
        try:
            self.probe_operation_queue(self.pool)
        except Exception:
            self.operation_queue_available = False
            self.operation_queue_reason_code = "operation_queue_unavailable"
            return
        self.operation_queue_available = True
        self.operation_queue_reason_code = None

    def close(self) -> None:
        """Close the process-owned pool when one exists."""
        if self.pool is not None:
            self.pool.close()

    def public_status(self) -> RuntimeStatusResponse:
        """Return sanitized component status without topology details."""
        self.refresh()
        authentication = RuntimeComponentStatus(
            component="authentication",
            status="available" if self.authentication_configured else "unavailable",
            reason_code=None if self.authentication_configured else "authentication_not_configured",
        )
        database = RuntimeComponentStatus(
            component="database",
            status="available" if self.database_available else "unavailable",
            reason_code=self.database_reason_code,
        )
        queue = RuntimeComponentStatus(
            component="operation_queue",
            status="available" if self.operation_queue_available else "unavailable",
            reason_code=self.operation_queue_reason_code,
        )
        components = (
            RuntimeComponentStatus(component="api", status="available"),
            authentication,
            database,
            queue,
        )
        aggregate: RuntimeAvailability = (
            "available" if all(item.status == "available" for item in components) else "degraded"
        )
        return RuntimeStatusResponse(status=aggregate, components=components)


class AvailabilityGuardedOperationQueue:
    """Keep operation reads available while rejecting new queued work."""

    def __init__(self, queue: OperationQueue, *, available: Callable[[], bool]) -> None:
        """Wrap a queue with a dynamic mutation availability check."""
        self._queue = queue
        self._available = available

    def enqueue(
        self,
        *,
        operation_type: str,
        owner_user_id: str,
        idempotency_key: str,
        request_payload: dict[str, Any],
        llm_mode: str | None,
        game_id: str | None = None,
        player_id: str | None = None,
        expected_version: int | None = None,
    ) -> QueuedOperation:
        """Reject mutations with a safe recovery path when the queue is unavailable."""
        if not self._available():
            raise AppError(
                "処理キューを利用できないため、新しい操作を受け付けられません。",
                code=ErrorCode.API_UNAVAILABLE,
                retryable=True,
            )
        return self._queue.enqueue(
            operation_type=operation_type,
            owner_user_id=owner_user_id,
            idempotency_key=idempotency_key,
            request_payload=request_payload,
            llm_mode=llm_mode,
            game_id=game_id,
            player_id=player_id,
            expected_version=expected_version,
        )

    def get(self, operation_id: str, *, owner_user_id: str) -> QueuedOperation | None:
        """Keep read-only operation status available through the concrete queue."""
        return self._queue.get(operation_id, owner_user_id=owner_user_id)


__all__ = ["AvailabilityGuardedOperationQueue", "RuntimeDependencies"]
