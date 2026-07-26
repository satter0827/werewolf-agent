"""Typer command handlers for game workflows."""

from __future__ import annotations

import logging
from typing import Annotated

import typer

from werewolf_agent.adapters.factory import build_public_client
from werewolf_agent.clients.cli.commands.common import _output_format
from werewolf_agent.clients.cli.errors import run_app_command
from werewolf_agent.clients.cli.messages import (
    HELP_OUTPUT_FORMAT,
)
from werewolf_agent.clients.cli.output import (
    print_setup_options,
)
from werewolf_agent.settings import get_settings

logger = logging.getLogger(__name__)


def setup_options(
    output: Annotated[
        str | None,
        typer.Option("--output", help=HELP_OUTPUT_FORMAT),
    ] = None,
) -> None:
    """Print default game setup metadata."""
    run_app_command(
        lambda: print_setup_options(
            build_public_client(get_settings()).get_runtime_config().setup,
            output_format=_output_format(output, get_settings()),
        )
    )
