"""Error handling helpers for CLI commands."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

import typer

from werewolf_agent.clients.cli.events import (
    LOG_CLI_APPLICATION_ERROR_HANDLED,
    LOG_CLI_UNHANDLED_EXCEPTION,
)
from werewolf_agent.clients.cli.messages import (
    message_error_line,
)
from werewolf_agent.clients.presentation import present_error
from werewolf_agent.contracts import AppError, InternalError
from werewolf_agent.contracts.error_catalog import get_error_spec
from werewolf_agent.observability.constants import EVENT_OUTCOME_FAILURE
from werewolf_agent.observability.levels import log_level_number
from werewolf_agent.security.redaction import redact_text

T = TypeVar("T")
logger = logging.getLogger(__name__)


def run_app_command(command: Callable[[], T]) -> T:
    """Run a command and translate safe app errors into CLI failures."""
    try:
        return command()
    except AppError as exc:
        logger.log(
            log_level_number(get_error_spec(exc.code).log_level),
            LOG_CLI_APPLICATION_ERROR_HANDLED,
            extra={
                **exc.log_extra(),
                "error_message": redact_text(exc.detail),
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
    presentation = present_error(error, language="ja")
    suffix = ""
    if presentation.next_action:
        suffix = f"{suffix} 必要な対応: {presentation.next_action}"
    return message_error_line(redact_text(presentation.detail), suffix)
