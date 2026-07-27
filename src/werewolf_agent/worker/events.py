"""Workerが記録するlog event名."""

from typing import Final

LOG_WORKER_APPLICATION_ERROR_HANDLED: Final = "worker.application_error.handled"
LOG_WORKER_APPLICATION_STARTED: Final = "worker.application.started"
LOG_WORKER_APPLICATION_STOPPED: Final = "worker.application.stopped"
LOG_WORKER_DATABASE_UNAVAILABLE: Final = "worker.database.unavailable"
LOG_WORKER_REQUEST_CLAIMED: Final = "worker.request.claimed"
LOG_WORKER_REQUEST_COMPLETED: Final = "worker.request.completed"
LOG_WORKER_REQUEST_FAILED: Final = "worker.request.failed"
LOG_WORKER_REQUEST_RETRY_STARTED: Final = "worker.request.retry_started"
LOG_WORKER_REQUEST_RETRY_SCHEDULED: Final = "worker.request.retry_scheduled"
LOG_WORKER_REQUEST_RETRY_EXHAUSTED: Final = "worker.request.retry_exhausted"

__all__ = [
    "LOG_WORKER_APPLICATION_ERROR_HANDLED",
    "LOG_WORKER_APPLICATION_STARTED",
    "LOG_WORKER_APPLICATION_STOPPED",
    "LOG_WORKER_DATABASE_UNAVAILABLE",
    "LOG_WORKER_REQUEST_CLAIMED",
    "LOG_WORKER_REQUEST_COMPLETED",
    "LOG_WORKER_REQUEST_FAILED",
    "LOG_WORKER_REQUEST_RETRY_EXHAUSTED",
    "LOG_WORKER_REQUEST_RETRY_SCHEDULED",
    "LOG_WORKER_REQUEST_RETRY_STARTED",
]
