"""Error handling helpers for CLI commands."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

import typer

from werewolf_agent.configuration.constants import EVENT_OUTCOME_FAILURE
from werewolf_agent.configuration.messages import (
    LOG_CLI_APPLICATION_ERROR_HANDLED,
    LOG_CLI_UNHANDLED_EXCEPTION,
    message_error_line,
)
from werewolf_agent.contracts import AppError, InternalError
from werewolf_agent.observability.levels import log_level_number
from werewolf_agent.security.redaction import redact_mapping, redact_text

T = TypeVar("T")
logger = logging.getLogger(__name__)


def run_app_command(command: Callable[[], T]) -> T:
    """Run a command and translate safe app errors into CLI failures."""
    try:
        return command()
    except AppError as exc:
        logger.log(
            log_level_number(exc.spec.log_level),
            LOG_CLI_APPLICATION_ERROR_HANDLED,
            extra={
                **exc.log_extra(),
                "error.message": redact_text(exc.detail),
                "event_action": LOG_CLI_APPLICATION_ERROR_HANDLED,
                "event_outcome": EVENT_OUTCOME_FAILURE,
            },
        )
        typer.echo(_safe_error_message(exc), err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        error = InternalError()
        logger.exception(
            LOG_CLI_UNHANDLED_EXCEPTION,
            extra={
                **error.log_extra(),
                "event_action": LOG_CLI_UNHANDLED_EXCEPTION,
                "event_outcome": EVENT_OUTCOME_FAILURE,
            },
        )
        typer.echo(_safe_error_message(error), err=True)
        raise typer.Exit(code=1) from exc


def _safe_error_message(error: AppError) -> str:
    context = redact_mapping(error.context)
    suffix = f" context={context}" if context else ""
    return message_error_line(error.detail, suffix)
