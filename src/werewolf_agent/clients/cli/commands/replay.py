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
    _load_replay_items,
    _output_format,
)
from werewolf_agent.clients.cli.constants import (
    CLI_OUTPUT_FORMAT_JSON,
    MIN_INTERVAL_SECONDS,
)
from werewolf_agent.clients.cli.errors import run_app_command
from werewolf_agent.clients.cli.events import (
    LOG_CLI_REPLAY_COMPLETED,
)
from werewolf_agent.clients.cli.messages import (
    HELP_GAME_ID_REPLAY,
    HELP_OUTPUT_FORMAT,
    HELP_REPLAY_DELAY,
    HELP_TIMELINE_FILE,
    MESSAGE_POLL_INTERVAL_MUST_BE_NON_NEGATIVE,
)
from werewolf_agent.clients.cli.output import (
    OutputFormat,
    print_timeline,
)
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.observability.constants import (
    EVENT_OUTCOME_SUCCESS,
)
from werewolf_agent.settings import get_settings

logger = logging.getLogger(__name__)


def replay(
    timeline_file: Annotated[
        Path | None,
        typer.Option("--timeline", help=HELP_TIMELINE_FILE),
    ] = None,
    game_id: Annotated[
        str | None,
        typer.Option("--game-id", help=HELP_GAME_ID_REPLAY),
    ] = None,
    delay: Annotated[float, typer.Option(help=HELP_REPLAY_DELAY)] = (MIN_INTERVAL_SECONDS),
    output: Annotated[
        str | None,
        typer.Option("--output", help=HELP_OUTPUT_FORMAT),
    ] = None,
) -> None:
    """Replay public timeline items from JSONL or the active data source."""
    settings = get_settings()
    run_app_command(
        lambda: _replay(
            timeline_file=timeline_file,
            game_id=game_id,
            delay=delay,
            client=_client(),
            output_format=_output_format(output, settings),
            timeline_limit=settings.api_timeline_max_limit,
        )
    )


def _replay(
    *,
    timeline_file: Path | None,
    game_id: str | None,
    delay: float,
    client: GameClient,
    output_format: OutputFormat,
    timeline_limit: int,
) -> None:
    if delay < MIN_INTERVAL_SECONDS:
        raise AppError(
            MESSAGE_POLL_INTERVAL_MUST_BE_NON_NEGATIVE,
            code=ErrorCode.CONFIG_INVALID_VALUE,
        )
    replay_items = _load_replay_items(
        timeline_file,
        game_id=game_id,
        client=client,
        timeline_limit=timeline_limit,
    )
    if output_format == CLI_OUTPUT_FORMAT_JSON:
        for _ in replay_items:
            if delay:
                time.sleep(delay)
        print_timeline(replay_items, output_format=output_format)
        logger.info(
            LOG_CLI_REPLAY_COMPLETED,
            extra={
                "event_action": LOG_CLI_REPLAY_COMPLETED,
                "event_outcome": EVENT_OUTCOME_SUCCESS,
                "event_count": len(replay_items),
            },
        )
        return
    for item in replay_items:
        if delay:
            time.sleep(delay)
        print_timeline([item], output_format=output_format)
    logger.info(
        LOG_CLI_REPLAY_COMPLETED,
        extra={
            "event_action": LOG_CLI_REPLAY_COMPLETED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "event_count": len(replay_items),
        },
    )
