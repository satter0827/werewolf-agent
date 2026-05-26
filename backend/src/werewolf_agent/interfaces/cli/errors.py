"""CLI error handling helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

import typer

from werewolf_agent.contracts import AppError

T = TypeVar("T")

logger = logging.getLogger(__name__)


def run_app_command(command: Callable[[], T]) -> T:
    """Run one CLI command body with shared application error handling."""
    try:
        return command()
    except AppError as exc:
        logger.error("Command failed", extra=exc.log_extra())
        typer.echo(f"Error: {exc.detail}", err=True)
        raise typer.Exit(code=1) from exc
