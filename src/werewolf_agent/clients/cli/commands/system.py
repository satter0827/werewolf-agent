"""CLI commands for runtime diagnosis."""

from __future__ import annotations

from typing import Annotated

import typer

from werewolf_agent.adapters.factory import build_public_client
from werewolf_agent.clients.cli.commands.common import _output_format
from werewolf_agent.clients.cli.errors import run_app_command
from werewolf_agent.clients.cli.messages import HELP_OUTPUT_FORMAT
from werewolf_agent.clients.cli.output import print_runtime_status
from werewolf_agent.settings import get_settings


def status(
    output: Annotated[
        str | None,
        typer.Option("--output", help=HELP_OUTPUT_FORMAT),
    ] = None,
) -> None:
    """Display current API and dependency availability."""
    settings = get_settings()
    run_app_command(
        lambda: print_runtime_status(
            build_public_client(settings).get_runtime_status(),
            output_format=_output_format(output, settings),
        )
    )


__all__ = ["status"]
