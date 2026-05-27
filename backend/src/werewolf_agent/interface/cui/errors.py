"""Error handling helpers for CUI commands."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import typer

from werewolf_agent.commons.security.redaction import redact_mapping
from werewolf_agent.contracts import AppError, InternalError

T = TypeVar("T")


def run_app_command(command: Callable[[], T]) -> T:
    """Run a command and translate safe app errors into CLI failures."""
    try:
        return command()
    except AppError as exc:
        typer.echo(_safe_error_message(exc), err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        error = InternalError()
        typer.echo(_safe_error_message(error), err=True)
        raise typer.Exit(code=1) from exc


def _safe_error_message(error: AppError) -> str:
    context = redact_mapping(error.context)
    suffix = f" context={context}" if context else ""
    return f"Error: {error.detail}{suffix}"
