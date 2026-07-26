"""Typer command handlers for game workflows."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel

from werewolf_agent.adapters.ports import GameClient
from werewolf_agent.clients.cli.commands.common import (
    _client,
    _create_request,
    _output_format,
)
from werewolf_agent.clients.cli.constants import (
    CLI_OUTPUT_FORMAT_TABLE,
    MIN_PAGE_OFFSET,
)
from werewolf_agent.clients.cli.errors import run_app_command
from werewolf_agent.clients.cli.events import (
    LOG_CLI_GAME_CREATED,
)
from werewolf_agent.clients.cli.messages import (
    HELP_GAME_ID_INSPECT,
    HELP_GAME_LIST_LIMIT,
    HELP_GAME_PAGE_OFFSET,
    HELP_GAME_STATUS_FILTER,
    HELP_MANUAL_PLAYER,
    HELP_OUTPUT_FORMAT,
    HELP_ROLE_COUNT,
    HELP_SEED,
    message_created_game,
    message_next_offset,
)
from werewolf_agent.clients.cli.output import (
    OutputFormat,
    console,
    print_game_summaries,
    print_json,
    print_state,
)
from werewolf_agent.observability.constants import (
    EVENT_OUTCOME_SUCCESS,
)
from werewolf_agent.settings import get_settings

logger = logging.getLogger(__name__)


def new(
    seed: Annotated[int | None, typer.Option(help=HELP_SEED)] = None,
    manual_player: Annotated[
        str | None,
        typer.Option("--manual-player", help=HELP_MANUAL_PLAYER),
    ] = None,
    role_count: Annotated[
        list[str] | None,
        typer.Option("--role-count", help=HELP_ROLE_COUNT),
    ] = None,
    rule_composition: Annotated[
        Path | None,
        typer.Option(
            "--rule-composition",
            help="rule compositionを記述したTOML file",
        ),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", help=HELP_OUTPUT_FORMAT),
    ] = None,
) -> None:
    """Create one game through the active data source."""
    run_app_command(
        lambda: _new(
            seed=seed,
            manual_player=manual_player,
            role_count=role_count or [],
            rule_composition_file=rule_composition,
            output_format=_output_format(output, get_settings()),
        )
    )


def _new(
    *,
    seed: int | None,
    manual_player: str | None,
    role_count: list[str],
    rule_composition_file: Path | None = None,
    output_format: OutputFormat,
    client: GameClient | None = None,
) -> None:
    request = _create_request(
        seed=seed,
        manual_player=manual_player,
        role_count=role_count,
        rule_composition_file=rule_composition_file,
    )
    api = client or _client()
    created = api.create_game(request)
    logger.info(
        LOG_CLI_GAME_CREATED,
        extra={
            "event_action": LOG_CLI_GAME_CREATED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_id": created.game_id,
            "has_manual_player": manual_player is not None,
        },
    )
    if output_format != CLI_OUTPUT_FORMAT_TABLE:
        print_json(created, output_format=output_format)
        return
    console.print(Panel.fit(message_created_game(created.game_id)))
    print_state(created.state)


def show(
    game_id: Annotated[str, typer.Argument(help=HELP_GAME_ID_INSPECT)],
    output: Annotated[
        str | None,
        typer.Option("--output", help=HELP_OUTPUT_FORMAT),
    ] = None,
) -> None:
    """Print public game state."""
    run_app_command(
        lambda: print_state(
            _client().get_game(game_id).state,
            output_format=_output_format(output, get_settings()),
        )
    )


def games(
    status: Annotated[str | None, typer.Option(help=HELP_GAME_STATUS_FILTER)] = None,
    limit: Annotated[int | None, typer.Option(help=HELP_GAME_LIST_LIMIT)] = None,
    offset: Annotated[int, typer.Option(help=HELP_GAME_PAGE_OFFSET)] = MIN_PAGE_OFFSET,
    output: Annotated[
        str | None,
        typer.Option("--output", help=HELP_OUTPUT_FORMAT),
    ] = None,
) -> None:
    """List public game summaries."""
    run_app_command(
        lambda: _games(
            status=status,
            limit=limit,
            offset=offset,
            client=_client(),
            output_format=_output_format(output, get_settings()),
        )
    )


def _games(
    *,
    status: str | None,
    limit: int | None,
    offset: int,
    client: GameClient,
    output_format: OutputFormat,
) -> None:
    response = client.list_games(status=status, limit=limit, offset=offset)
    print_game_summaries(response.games, output_format=output_format)
    if response.next_offset is not None and output_format == CLI_OUTPUT_FORMAT_TABLE:
        console.print(message_next_offset(response.next_offset))
