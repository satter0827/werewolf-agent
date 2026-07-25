"""Typer command handlers for game workflows."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Annotated

import typer

from werewolf_agent.adapters.ports import GameClient
from werewolf_agent.clients.cli.commands.common import (
    _client,
    _output_format,
)
from werewolf_agent.clients.cli.constants import (
    CLI_OUTPUT_FORMAT_JSON,
    MIN_INTERVAL_SECONDS,
    MIN_PAGE_OFFSET,
)
from werewolf_agent.clients.cli.errors import run_app_command
from werewolf_agent.clients.cli.events import (
    LOG_CLI_TIMELINE_POLLED,
)
from werewolf_agent.clients.cli.messages import (
    HELP_AFTER_SEQUENCE,
    HELP_FOLLOW,
    HELP_GAME_ID_INSPECT,
    HELP_LIMIT_PER_POLL,
    HELP_LOG_JSONL,
    HELP_OUTPUT_FORMAT,
    HELP_POLL_INTERVAL_FOLLOW,
    MESSAGE_JSON_OUTPUT_CANNOT_FOLLOW,
    MESSAGE_POLL_INTERVAL_MUST_BE_NON_NEGATIVE,
)
from werewolf_agent.clients.cli.output import (
    OutputFormat,
    consume_timeline,
)
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.observability.constants import (
    EVENT_OUTCOME_SUCCESS,
)
from werewolf_agent.settings import get_settings

logger = logging.getLogger(__name__)


def timeline(
    game_id: Annotated[str, typer.Argument(help=HELP_GAME_ID_INSPECT)],
    after: Annotated[int, typer.Option(help=HELP_AFTER_SEQUENCE)] = (MIN_PAGE_OFFSET),
    limit: Annotated[int | None, typer.Option(help=HELP_LIMIT_PER_POLL)] = None,
    poll_interval: Annotated[
        float | None,
        typer.Option(help=HELP_POLL_INTERVAL_FOLLOW),
    ] = None,
    follow: Annotated[
        bool,
        typer.Option("--follow/--no-follow", help=HELP_FOLLOW),
    ] = False,
    log_jsonl: Annotated[Path | None, typer.Option(help=HELP_LOG_JSONL)] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", help=HELP_OUTPUT_FORMAT),
    ] = None,
) -> None:
    """Read or follow public game timeline items."""
    settings = get_settings()
    run_app_command(
        lambda: _timeline(
            game_id=game_id,
            after=after,
            limit=limit or settings.cli_event_limit,
            poll_interval=(
                settings.cli_poll_interval_seconds if poll_interval is None else poll_interval
            ),
            follow=follow,
            log_jsonl=log_jsonl,
            client=_client(),
            output_format=_output_format(output, settings),
        )
    )


def _timeline(
    *,
    game_id: str,
    after: int,
    limit: int,
    poll_interval: float,
    follow: bool,
    log_jsonl: Path | None,
    client: GameClient,
    output_format: OutputFormat,
) -> None:
    if follow and output_format == CLI_OUTPUT_FORMAT_JSON:
        raise AppError(MESSAGE_JSON_OUTPUT_CANNOT_FOLLOW, code=ErrorCode.CONFIG_INVALID_VALUE)
    if poll_interval < MIN_INTERVAL_SECONDS:
        raise AppError(
            MESSAGE_POLL_INTERVAL_MUST_BE_NON_NEGATIVE,
            code=ErrorCode.CONFIG_INVALID_VALUE,
        )

    last_sequence = after
    while True:
        previous_sequence = last_sequence
        batch = client.get_timeline(game_id, after=last_sequence, limit=limit)
        last_sequence = consume_timeline(
            batch.items,
            next_after=batch.next_after,
            log_jsonl=log_jsonl,
            show_items=True,
            output_format=output_format,
        )
        logger.debug(
            LOG_CLI_TIMELINE_POLLED,
            extra={
                "event_action": LOG_CLI_TIMELINE_POLLED,
                "event_outcome": EVENT_OUTCOME_SUCCESS,
                "game_id": game_id,
                "after": previous_sequence,
                "next_after": last_sequence,
                "event_count": len(batch.items),
            },
        )
        if not follow:
            return
        time.sleep(poll_interval)
