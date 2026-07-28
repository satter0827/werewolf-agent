"""Typer command handlers for game workflows."""

from __future__ import annotations

import logging
from typing import Annotated

import typer
from rich.table import Table

from werewolf_agent.adapters.factory import build_public_client
from werewolf_agent.clients.cli.commands.common import (
    _output_format,
)
from werewolf_agent.clients.cli.constants import (
    CLI_OUTPUT_FORMAT_TABLE,
    HEALTH_STATUS_OK,
)
from werewolf_agent.clients.cli.errors import run_app_command
from werewolf_agent.clients.cli.messages import (
    COLUMN_CHECK,
    COLUMN_VALUE,
    HELP_OUTPUT_FORMAT,
    TABLE_TITLE_DOCTOR,
)
from werewolf_agent.clients.cli.output import (
    console,
    print_json,
)
from werewolf_agent.contracts import AppError
from werewolf_agent.settings import get_settings
from werewolf_agent.settings.diagnostics import build_entrypoint_diagnostics

logger = logging.getLogger(__name__)


def doctor(
    output: Annotated[
        str | None,
        typer.Option("--output", help=HELP_OUTPUT_FORMAT),
    ] = None,
) -> None:
    """Print local development environment diagnostics."""
    run_app_command(lambda: _doctor(output=output))


def _doctor(*, output: str | None) -> None:
    settings = get_settings()
    output_format = _output_format(output, settings)
    try:
        health = build_public_client(settings).health()
    except AppError as exc:
        api_health = exc.detail
    else:
        api_health = health.get("status", HEALTH_STATUS_OK)
    checks = build_entrypoint_diagnostics(
        settings=settings,
        data_source=health.get("service", "supabase") if "health" in locals() else "supabase",
        api_health=api_health,
    )

    if output_format != CLI_OUTPUT_FORMAT_TABLE:
        print_json(checks, output_format=output_format)
        return

    table = Table(title=TABLE_TITLE_DOCTOR)
    table.add_column(COLUMN_CHECK, style="cyan", no_wrap=True)
    table.add_column(COLUMN_VALUE, overflow="fold")
    for key, value in checks.items():
        table.add_row(key, value)
    console.print(table)
