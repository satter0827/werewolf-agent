"""Administrator-only CLI commands."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

import typer
from pydantic import BaseModel

from werewolf_agent.adapters.factory import build_admin_client
from werewolf_agent.clients.cli.commands.common import _output_format
from werewolf_agent.clients.cli.errors import run_app_command
from werewolf_agent.clients.cli.messages import HELP_OUTPUT_FORMAT
from werewolf_agent.clients.cli.output import print_json
from werewolf_agent.settings import get_settings


def _run(loader: Callable[[], BaseModel], output: str | None) -> None:
    settings = get_settings()
    run_app_command(lambda: print_json(loader(), output_format=_output_format(output, settings)))


def reveal(
    game_id: Annotated[str, typer.Argument(help="対象のgame ID")],
    output: Annotated[str | None, typer.Option("--output", help=HELP_OUTPUT_FORMAT)] = None,
) -> None:
    """Return the complete authorized game state."""
    _run(lambda: build_admin_client(get_settings()).reveal_game(game_id), output)


def replay_verify(
    game_id: Annotated[str, typer.Argument(help="対象のgame ID")],
    output: Annotated[str | None, typer.Option("--output", help=HELP_OUTPUT_FORMAT)] = None,
) -> None:
    """Verify the deterministic replay of one stored game."""
    _run(lambda: build_admin_client(get_settings()).verify_replay(game_id), output)


def operation(
    operation_id: Annotated[str, typer.Argument(help="対象のoperation ID")],
    output: Annotated[str | None, typer.Option("--output", help=HELP_OUTPUT_FORMAT)] = None,
) -> None:
    """Return bounded diagnostics for one operation."""
    _run(lambda: build_admin_client(get_settings()).diagnose_operation(operation_id), output)


def llm_traces(
    game_id: Annotated[str, typer.Argument(help="対象のgame ID")],
    limit: Annotated[int, typer.Option(help="取得する最大件数")] = 50,
    output: Annotated[str | None, typer.Option("--output", help=HELP_OUTPUT_FORMAT)] = None,
) -> None:
    """Return LLM trace metadata without private prompt content."""
    _run(
        lambda: build_admin_client(get_settings()).list_llm_traces(game_id, limit=limit),
        output,
    )


def llm_usage(
    game_id: Annotated[str, typer.Argument(help="対象のgame ID")],
    output: Annotated[str | None, typer.Option("--output", help=HELP_OUTPUT_FORMAT)] = None,
) -> None:
    """Return aggregate LLM usage for one game."""
    _run(lambda: build_admin_client(get_settings()).get_llm_usage(game_id), output)


__all__ = ["llm_traces", "llm_usage", "operation", "replay_verify", "reveal"]
