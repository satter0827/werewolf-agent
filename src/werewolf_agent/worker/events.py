"""Workerが記録するlog event名."""

from typing import Final

LOG_WORKER_APPLICATION_ERROR_HANDLED: Final = "worker.application_error.handled"
LOG_WORKER_APPLICATION_STARTED: Final = "worker.application.started"
LOG_WORKER_DATABASE_UNAVAILABLE: Final = "worker.database.unavailable"
LOG_WORKER_REQUEST_CLAIMED: Final = "worker.request.claimed"
LOG_WORKER_REQUEST_COMPLETED: Final = "worker.request.completed"
LOG_WORKER_REQUEST_FAILED: Final = "worker.request.failed"

__all__ = [
    "LOG_WORKER_APPLICATION_ERROR_HANDLED",
    "LOG_WORKER_APPLICATION_STARTED",
    "LOG_WORKER_DATABASE_UNAVAILABLE",
    "LOG_WORKER_REQUEST_CLAIMED",
    "LOG_WORKER_REQUEST_COMPLETED",
    "LOG_WORKER_REQUEST_FAILED",
]
