"""Typer command handlers for game workflows."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel

from werewolf_agent.adapters.ports import GameClient
from werewolf_agent.clients.cli.commands.common import (
    _client,
    _create_request,
    _output_format,
    _prompt_and_submit_manual_action,
)
from werewolf_agent.clients.cli.constants import (
    CLI_OUTPUT_FORMAT_JSON,
    CLI_OUTPUT_FORMAT_TABLE,
    MIN_INTERVAL_SECONDS,
    MIN_PAGE_OFFSET,
    MIN_STEP_LIMIT,
    UNKNOWN_VALUE_LABEL,
)
from werewolf_agent.clients.cli.errors import run_app_command
from werewolf_agent.clients.cli.events import (
    LOG_CLI_PLAY_COMPLETED,
)
from werewolf_agent.clients.cli.messages import (
    HELP_GAME_ID_ADVANCE,
    HELP_LOG_JSONL,
    HELP_MANUAL_PLAYER,
    HELP_MAX_STEPS,
    HELP_OUTPUT_FORMAT,
    HELP_POLL_INTERVAL_STEPS,
    HELP_ROLE_COUNT,
    HELP_SEED,
    HELP_SHOW_TIMELINE,
    MESSAGE_MAX_STEPS_MUST_BE_AT_LEAST_ONE,
    MESSAGE_POLL_INTERVAL_MUST_BE_NON_NEGATIVE,
    message_created_game,
    message_game_completed,
    message_game_did_not_complete,
)
from werewolf_agent.clients.cli.output import (
    OutputFormat,
    console,
    consume_timeline,
    print_json,
    print_state,
    print_timeline,
)
from werewolf_agent.contracts import GAME_STATUS_COMPLETED, AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    GameTimelineItem,
)
from werewolf_agent.observability.constants import (
    EVENT_OUTCOME_SUCCESS,
)
from werewolf_agent.settings import get_settings

logger = logging.getLogger(__name__)


def advance(
    game_id: Annotated[str, typer.Argument(help=HELP_GAME_ID_ADVANCE)],
    output: Annotated[
        str | None,
        typer.Option("--output", help=HELP_OUTPUT_FORMAT),
    ] = None,
) -> None:
    """Advance one game by one data-source step."""
    run_app_command(
        lambda: _advance(
            game_id=game_id,
            client=_client(),
            output_format=_output_format(output, get_settings()),
        )
    )


def _advance(*, game_id: str, client: GameClient, output_format: OutputFormat) -> None:
    response = client.advance_game(game_id)
    if output_format != CLI_OUTPUT_FORMAT_TABLE:
        print_json(response, output_format=output_format)
        return
    print_state(response.state)
    print_timeline(response.timeline)


def play(
    seed: Annotated[int | None, typer.Option(help=HELP_SEED)] = None,
    manual_player: Annotated[
        str | None,
        typer.Option("--manual-player", help=HELP_MANUAL_PLAYER),
    ] = None,
    max_steps: Annotated[int | None, typer.Option(help=HELP_MAX_STEPS)] = None,
    role_count: Annotated[
        list[str] | None,
        typer.Option("--role-count", help=HELP_ROLE_COUNT),
    ] = None,
    log_jsonl: Annotated[Path | None, typer.Option(help=HELP_LOG_JSONL)] = None,
    poll_interval: Annotated[
        float | None,
        typer.Option(help=HELP_POLL_INTERVAL_STEPS),
    ] = None,
    show_timeline: Annotated[
        bool,
        typer.Option("--show-timeline/--no-show-timeline", help=HELP_SHOW_TIMELINE),
    ] = True,
    output: Annotated[
        str | None,
        typer.Option("--output", help=HELP_OUTPUT_FORMAT),
    ] = None,
) -> None:
    """Create and run one game through the active data source."""
    settings = get_settings()
    run_app_command(
        lambda: _play(
            seed=seed,
            manual_player=manual_player,
            role_count=role_count or [],
            max_steps=max_steps or settings.cli_max_steps,
            log_jsonl=log_jsonl,
            poll_interval=(
                settings.cli_poll_interval_seconds if poll_interval is None else poll_interval
            ),
            show_timeline=show_timeline,
            output_format=_output_format(output, settings),
        )
    )


def _play(
    *,
    seed: int | None,
    manual_player: str | None,
    role_count: list[str],
    max_steps: int,
    log_jsonl: Path | None,
    poll_interval: float,
    show_timeline: bool,
    output_format: OutputFormat,
    client: GameClient | None = None,
) -> None:
    if max_steps < MIN_STEP_LIMIT:
        raise AppError(MESSAGE_MAX_STEPS_MUST_BE_AT_LEAST_ONE, code=ErrorCode.CONFIG_INVALID_VALUE)
    if poll_interval < MIN_INTERVAL_SECONDS:
        raise AppError(
            MESSAGE_POLL_INTERVAL_MUST_BE_NON_NEGATIVE,
            code=ErrorCode.CONFIG_INVALID_VALUE,
        )

    request = _create_request(
        seed=seed,
        manual_player=manual_player,
        role_count=role_count,
    )
    api = client or _client()
    created = api.create_game(request)
    state = created.state
    last_sequence = MIN_PAGE_OFFSET
    emitted_items: list[GameTimelineItem] = []

    if output_format == CLI_OUTPUT_FORMAT_TABLE:
        console.print(Panel.fit(message_created_game(created.game_id)))
        print_state(state)

    initial_timeline = api.get_timeline(created.game_id, after=last_sequence)
    emitted_items.extend(initial_timeline.items)
    last_sequence = consume_timeline(
        initial_timeline.items,
        next_after=initial_timeline.next_after,
        log_jsonl=log_jsonl,
        show_items=show_timeline and output_format != CLI_OUTPUT_FORMAT_JSON,
        output_format=output_format,
    )

    steps = 0
    while state.status != GAME_STATUS_COMPLETED and steps < max_steps:
        if manual_player is not None:
            _prompt_and_submit_manual_action(
                client=api,
                game_id=created.game_id,
                player_id=manual_player,
                output_format=output_format,
            )
        if poll_interval:
            time.sleep(poll_interval)
        state = api.advance_game(created.game_id).state
        steps += 1

        timeline_batch = api.get_timeline(created.game_id, after=last_sequence)
        emitted_items.extend(timeline_batch.items)
        last_sequence = consume_timeline(
            timeline_batch.items,
            next_after=timeline_batch.next_after,
            log_jsonl=log_jsonl,
            show_items=show_timeline and output_format != CLI_OUTPUT_FORMAT_JSON,
            output_format=output_format,
        )

    if state.status != GAME_STATUS_COMPLETED:
        raise AppError(
            message_game_did_not_complete(max_steps),
            code=ErrorCode.CONFIG_INVALID_VALUE,
        )

    winner = state.winner or UNKNOWN_VALUE_LABEL
    logger.info(
        LOG_CLI_PLAY_COMPLETED,
        extra={
            "event_action": LOG_CLI_PLAY_COMPLETED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_id": created.game_id,
            "winner": winner,
            "steps": steps,
        },
    )
    if output_format == CLI_OUTPUT_FORMAT_TABLE:
        print_state(state)
        console.print(message_game_completed(winner=winner, steps=steps))
    elif output_format == CLI_OUTPUT_FORMAT_JSON:
        print_json(
            {
                "game_id": created.game_id,
                "winner": winner,
                "steps": steps,
                "state": state,
                "timeline": emitted_items if show_timeline else [],
            },
            output_format=output_format,
        )
    else:
        print_json(
            {"game_id": created.game_id, "winner": winner, "steps": steps},
            output_format=output_format,
        )
