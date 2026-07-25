"""Typer interface for the Supabase worker process."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

import typer

from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.observability import configure_entrypoint_logging
from werewolf_agent.observability.constants import (
    EVENT_OUTCOME_FAILURE,
    EVENT_OUTCOME_SUCCESS,
)
from werewolf_agent.observability.levels import log_level_number
from werewolf_agent.security.redaction import redact_text
from werewolf_agent.settings import (
    AppSettings,
    get_settings,
)
from werewolf_agent.worker.events import (
    LOG_WORKER_APPLICATION_ERROR_HANDLED,
    LOG_WORKER_APPLICATION_STARTED,
)
from werewolf_agent.worker.messages import (
    MESSAGE_SUPABASE_WORKER_DSN_REQUIRED,
    message_error_line,
)
from werewolf_agent.worker.service import process_worker_batch, run_worker_forever

app = typer.Typer(no_args_is_help=True, help="Run Supabase request queue workers.")
logger = logging.getLogger(__name__)
T = TypeVar("T")


@app.command()
def once() -> None:
    """Process one configured worker batch and exit."""
    _run_worker_command(lambda: _once())


@app.command()
def run() -> None:
    """Run the worker loop until interrupted."""
    _run_worker_command(_run)


def _once() -> None:
    settings = get_settings()
    configure_entrypoint_logging(
        settings,
        default_log_file_name="worker.jsonl",
        service_name="werewolf-agent-worker",
    )
    _require_worker_config(settings)
    _log_worker_started(settings, mode="once")
    processed = process_worker_batch(settings)
    typer.echo(f"processed={processed}")


def _run() -> None:
    settings = get_settings()
    configure_entrypoint_logging(
        settings,
        default_log_file_name="worker.jsonl",
        service_name="werewolf-agent-worker",
    )
    _require_worker_config(settings)
    _log_worker_started(settings, mode="run")
    run_worker_forever(settings)


def _require_worker_config(settings: AppSettings) -> None:
    if settings.supabase_worker_configured:
        return
    raise AppError(MESSAGE_SUPABASE_WORKER_DSN_REQUIRED, code=ErrorCode.CONFIG_INVALID_VALUE)


def _log_worker_started(settings: AppSettings, *, mode: str) -> None:
    logger.info(
        LOG_WORKER_APPLICATION_STARTED,
        extra={
            "event_action": LOG_WORKER_APPLICATION_STARTED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "worker_id": settings.supabase_worker_id,
            "worker_mode": mode,
            "worker_batch_size": settings.supabase_worker_batch_size,
            "worker_poll_interval_seconds": settings.supabase_worker_poll_interval_seconds,
        },
    )


def _run_worker_command(command: Callable[[], T]) -> T:
    try:
        return command()
    except AppError as exc:
        logger.log(
            log_level_number(exc.spec.log_level),
            LOG_WORKER_APPLICATION_ERROR_HANDLED,
            extra={
                **exc.log_extra(),
                "error.message": redact_text(exc.detail),
                "event_action": LOG_WORKER_APPLICATION_ERROR_HANDLED,
                "event_outcome": EVENT_OUTCOME_FAILURE,
            },
        )
        typer.echo(message_error_line(exc.detail), err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
