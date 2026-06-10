"""Typer command handlers for local development workflows."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from rich.panel import Panel
from rich.table import Table

from werewolf_agent.api.factory import build_game_api
from werewolf_agent.api.ports import GameApi
from werewolf_agent.commons.configuration import AppSettings, get_settings
from werewolf_agent.commons.diagnostics import build_entrypoint_diagnostics
from werewolf_agent.commons.shared.constants import (
    CLI_OUTPUT_FORMAT_CHOICE_SET,
    CLI_OUTPUT_FORMAT_JSON,
    CLI_OUTPUT_FORMAT_TABLE,
    EVENT_OUTCOME_SUCCESS,
    HEALTH_STATUS_OK,
    MIN_INTERVAL_SECONDS,
    MIN_PAGE_OFFSET,
    MIN_STEP_LIMIT,
    UNKNOWN_VALUE_LABEL,
)
from werewolf_agent.commons.shared.messages import (
    LOG_CLI_ACTION_SUBMITTED,
    LOG_CLI_GAME_CREATED,
    LOG_CLI_PLAY_COMPLETED,
    LOG_CLI_REPLAY_COMPLETED,
    LOG_CLI_TIMELINE_POLLED,
    MESSAGE_JSON_OUTPUT_CANNOT_FOLLOW,
    MESSAGE_MAX_STEPS_MUST_BE_AT_LEAST_ONE,
    MESSAGE_OUTPUT_FORMAT_MUST_BE_VALID,
    MESSAGE_POLL_INTERVAL_MUST_BE_NON_NEGATIVE,
    message_game_did_not_complete,
)
from werewolf_agent.contracts import GAME_STATUS_COMPLETED, AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    CreateGameRequest,
    GameTimelineItem,
    PlayerActionRequest,
)
from werewolf_agent.entrypoint.cui.errors import run_app_command
from werewolf_agent.entrypoint.cui.messages import (
    COLUMN_CHECK,
    COLUMN_VALUE,
    HELP_AFTER_SEQUENCE,
    HELP_FOLLOW,
    HELP_GAME_ID_ADVANCE,
    HELP_GAME_ID_INSPECT,
    HELP_GAME_ID_REPLAY,
    HELP_GAME_LIST_LIMIT,
    HELP_GAME_PAGE_OFFSET,
    HELP_GAME_STATUS_FILTER,
    HELP_LIMIT_PER_POLL,
    HELP_LOG_JSONL,
    HELP_MANUAL_PLAYER,
    HELP_MAX_STEPS,
    HELP_OUTPUT_FORMAT,
    HELP_POLL_INTERVAL_FOLLOW,
    HELP_POLL_INTERVAL_STEPS,
    HELP_REPLAY_DELAY,
    HELP_ROLE_COUNT,
    HELP_SEED,
    HELP_SHOW_TIMELINE,
    HELP_TIMELINE_FILE,
    MESSAGE_REPLAY_SOURCE_REQUIRED,
    PROMPT_SPEECH,
    TABLE_TITLE_DOCTOR,
    message_created_game,
    message_game_completed,
    message_next_offset,
    message_target_prompt,
)
from werewolf_agent.entrypoint.cui.output import (
    OutputFormat,
    console,
    consume_timeline,
    print_game_summaries,
    print_json,
    print_observation,
    print_setup_options,
    print_state,
    print_timeline,
)
from werewolf_agent.entrypoint.requests import (
    build_create_game_request,
    parse_role_counts,
)

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
        health = build_game_api(settings).health()
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


def setup_options(
    output: Annotated[
        str | None,
        typer.Option("--output", help=HELP_OUTPUT_FORMAT),
    ] = None,
) -> None:
    """Print default game setup metadata."""
    run_app_command(
        lambda: print_setup_options(
            _client().get_setup_options(),
            output_format=_output_format(output, get_settings()),
        )
    )


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
            output_format=_output_format(output, get_settings()),
        )
    )


def _new(
    *,
    seed: int | None,
    manual_player: str | None,
    role_count: list[str],
    output_format: OutputFormat,
    client: GameApi | None = None,
) -> None:
    request = _create_request(
        seed=seed,
        manual_player=manual_player,
        role_count=role_count,
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


def _advance(*, game_id: str, client: GameApi, output_format: OutputFormat) -> None:
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
    client: GameApi | None = None,
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
    client: GameApi,
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
    client: GameApi,
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
    client: GameApi,
    output_format: OutputFormat,
) -> None:
    response = client.list_games(status=status, limit=limit, offset=offset)
    print_game_summaries(response.games, output_format=output_format)
    if response.next_offset is not None and output_format == CLI_OUTPUT_FORMAT_TABLE:
        console.print(message_next_offset(response.next_offset))


def _client() -> GameApi:
    settings = get_settings()
    return build_game_api(settings)


def _create_request(
    *,
    seed: int | None,
    manual_player: str | None,
    role_count: list[str],
) -> CreateGameRequest:
    settings = get_settings()
    role_counts = (
        parse_role_counts(role_count)
        if role_count
        else settings.game_definitions.roles.default_counts_for(settings.game_default_player_count)
    )
    return build_create_game_request(
        seed=seed,
        manual_player_id=manual_player,
        role_counts=role_counts,
    )


def _prompt_and_submit_manual_action(
    *,
    client: GameApi,
    game_id: str,
    player_id: str,
    output_format: OutputFormat,
) -> None:
    observation = client.get_private_observation(
        game_id,
        player_id,
    )
    actions = observation.observation.get("available_actions") or []
    if not actions:
        return
    if output_format == CLI_OUTPUT_FORMAT_TABLE:
        print_observation(observation)
    action_type = str(actions[0])
    target_id = None
    message = None
    if action_type == "speech":
        message = typer.prompt(PROMPT_SPEECH)
    elif action_type != "pass":
        target_id = typer.prompt(message_target_prompt(action_type))
    response = client.submit_player_action(
        game_id,
        player_id,
        PlayerActionRequest(
            type=cast(Any, action_type),
            target_id=target_id,
            message=message,
        ),
    )
    logger.info(
        LOG_CLI_ACTION_SUBMITTED,
        extra={
            "event_action": LOG_CLI_ACTION_SUBMITTED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_id": game_id,
            "has_target": target_id is not None,
            "has_message": bool(message),
        },
    )
    if output_format == CLI_OUTPUT_FORMAT_TABLE:
        print_timeline(response.timeline)


def _load_replay_items(
    timeline_file: Path | None,
    *,
    game_id: str | None,
    client: GameApi,
    timeline_limit: int,
) -> list[GameTimelineItem]:
    if timeline_file is not None:
        return [
            GameTimelineItem.model_validate_json(line)
            for line in timeline_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if game_id is not None:
        return client.get_timeline(
            game_id,
            after=MIN_PAGE_OFFSET,
            limit=timeline_limit,
        ).items
    raise AppError(MESSAGE_REPLAY_SOURCE_REQUIRED, code=ErrorCode.CONFIG_INVALID_VALUE)


def _output_format(value: str | None, settings: AppSettings) -> OutputFormat:
    raw_value = value or settings.cli_output_format
    if raw_value not in CLI_OUTPUT_FORMAT_CHOICE_SET:
        raise AppError(MESSAGE_OUTPUT_FORMAT_MUST_BE_VALID, code=ErrorCode.CONFIG_INVALID_VALUE)
    return cast(OutputFormat, raw_value)
