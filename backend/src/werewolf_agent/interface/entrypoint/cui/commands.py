"""Typer command handlers for local development workflows."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from rich.panel import Panel
from rich.table import Table

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
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    CreateGameRequest,
    GameTimelineItem,
    PlayerActionRequest,
)
from werewolf_agent.interface.entrypoint.cui.errors import run_app_command
from werewolf_agent.interface.entrypoint.cui.output import (
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
from werewolf_agent.interface.runtime import AppSettings, get_settings
from werewolf_agent.interface.shared.api_client import GameApiClient, build_game_api_client
from werewolf_agent.interface.shared.diagnostics import build_interface_diagnostics
from werewolf_agent.interface.shared.game_requests import (
    build_create_game_request,
    parse_role_counts,
)

logger = logging.getLogger(__name__)


def doctor(
    api_url: Annotated[
        str | None,
        typer.Option(help="Base URL for the Werewolf Agent API."),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Output format: table, json, or jsonl."),
    ] = None,
) -> None:
    """Print local development environment diagnostics."""
    run_app_command(lambda: _doctor(api_url=api_url, output=output))


def _doctor(*, api_url: str | None, output: str | None) -> None:
    settings = get_settings()
    resolved_api_url = api_url or settings.cli_api_url
    output_format = _output_format(output, settings)
    try:
        health = _build_game_api_client(resolved_api_url).health()
    except AppError as exc:
        api_health = exc.detail
    else:
        api_health = health.get("status", "ok")
    checks = build_interface_diagnostics(
        settings=settings,
        api_url=resolved_api_url,
        api_health=api_health,
    )

    if output_format != "table":
        print_json(checks, output_format=output_format)
        return

    table = Table(title="Werewolf Agent Doctor")
    table.add_column("Check", style="cyan", no_wrap=True)
    table.add_column("Value", overflow="fold")
    for key, value in checks.items():
        table.add_row(key, value)
    console.print(table)


def setup_options(
    api_url: Annotated[
        str | None,
        typer.Option(help="Base URL for the Werewolf Agent API."),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Output format: table, json, or jsonl."),
    ] = None,
) -> None:
    """Print default game setup metadata."""
    run_app_command(
        lambda: print_setup_options(
            _client(api_url).get_setup_options(),
            output_format=_output_format(output, get_settings()),
        )
    )


def new(
    api_url: Annotated[str | None, typer.Option(help="Base URL for the API.")] = None,
    seed: Annotated[int | None, typer.Option(help="Deterministic seed.")] = None,
    manual_player: Annotated[
        str | None,
        typer.Option("--manual-player", help="Player id controlled by this CLI."),
    ] = None,
    role_count: Annotated[
        list[str] | None,
        typer.Option("--role-count", help="Role count entry, e.g. werewolf=1."),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Output format: table, json, or jsonl."),
    ] = None,
) -> None:
    """Create one game through the public HTTP API."""
    run_app_command(
        lambda: _new(
            seed=seed,
            manual_player=manual_player,
            role_count=role_count or [],
            client=_client(api_url),
            output_format=_output_format(output, get_settings()),
        )
    )


def _new(
    *,
    seed: int | None,
    manual_player: str | None,
    role_count: list[str],
    client: GameApiClient,
    output_format: OutputFormat,
) -> None:
    request = _create_request(
        seed=seed,
        manual_player=manual_player,
        role_count=role_count,
    )
    created = client.create_game(request)
    logger.info(
        LOG_CLI_GAME_CREATED,
        extra={
            "event_action": LOG_CLI_GAME_CREATED,
            "event_outcome": "success",
            "game_id": created.game_id,
            "has_manual_player": manual_player is not None,
        },
    )
    if output_format != "table":
        print_json(created, output_format=output_format)
        return
    console.print(Panel.fit(f"Created game [bold]{created.game_id}[/bold]"))
    print_state(created.state)
    if created.manual_player is not None:
        console.print(
            "[yellow]manual token[/yellow] "
            f"{created.manual_player.player_id}: {created.manual_player.token}"
        )


def show(
    game_id: Annotated[str, typer.Argument(help="Game id to inspect.")],
    api_url: Annotated[str | None, typer.Option(help="Base URL for the API.")] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Output format: table, json, or jsonl."),
    ] = None,
) -> None:
    """Print public game state."""
    run_app_command(
        lambda: print_state(
            _client(api_url).get_game(game_id).state,
            output_format=_output_format(output, get_settings()),
        )
    )


def advance(
    game_id: Annotated[str, typer.Argument(help="Game id to advance.")],
    api_url: Annotated[str | None, typer.Option(help="Base URL for the API.")] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Output format: table, json, or jsonl."),
    ] = None,
) -> None:
    """Advance one game by one API step."""
    run_app_command(
        lambda: _advance(
            game_id=game_id,
            client=_client(api_url),
            output_format=_output_format(output, get_settings()),
        )
    )


def _advance(*, game_id: str, client: GameApiClient, output_format: OutputFormat) -> None:
    response = client.advance_game(game_id)
    if output_format != "table":
        print_json(response, output_format=output_format)
        return
    print_state(response.state)
    print_timeline(response.timeline)


def play(
    api_url: Annotated[str | None, typer.Option(help="Base URL for the API.")] = None,
    seed: Annotated[int | None, typer.Option(help="Deterministic seed.")] = None,
    manual_player: Annotated[
        str | None,
        typer.Option("--manual-player", help="Player id controlled by this CLI."),
    ] = None,
    max_steps: Annotated[int | None, typer.Option(help="Maximum API step calls.")] = None,
    role_count: Annotated[
        list[str] | None,
        typer.Option("--role-count", help="Role count entry, e.g. werewolf=1."),
    ] = None,
    log_jsonl: Annotated[Path | None, typer.Option(help="Optional public timeline JSONL.")] = None,
    poll_interval: Annotated[
        float | None,
        typer.Option(help="Seconds to wait between API step calls."),
    ] = None,
    show_timeline: Annotated[
        bool,
        typer.Option("--show-timeline/--no-show-timeline", help="Print public timeline items."),
    ] = True,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Output format: table, json, or jsonl."),
    ] = None,
) -> None:
    """Create and run one game through the public HTTP API."""
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
            client=_client(api_url),
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
    client: GameApiClient,
    output_format: OutputFormat,
) -> None:
    if max_steps < 1:
        raise AppError(MESSAGE_MAX_STEPS_MUST_BE_AT_LEAST_ONE, code=ErrorCode.CONFIG_INVALID_VALUE)
    if poll_interval < 0:
        raise AppError(
            MESSAGE_POLL_INTERVAL_MUST_BE_NON_NEGATIVE,
            code=ErrorCode.CONFIG_INVALID_VALUE,
        )

    created = client.create_game(
        _create_request(
            seed=seed,
            manual_player=manual_player,
            role_count=role_count,
        )
    )
    state = created.state
    last_sequence = 0
    emitted_items: list[GameTimelineItem] = []
    manual_token = (
        created.manual_player.token
        if created.manual_player is not None and created.manual_player.player_id == manual_player
        else None
    )

    if output_format == "table":
        console.print(Panel.fit(f"Created game [bold]{created.game_id}[/bold]"))
        print_state(state)

    initial_timeline = client.get_timeline(created.game_id, after=last_sequence)
    emitted_items.extend(initial_timeline.items)
    last_sequence = consume_timeline(
        initial_timeline.items,
        next_after=initial_timeline.next_after,
        log_jsonl=log_jsonl,
        show_items=show_timeline and output_format != "json",
        output_format=output_format,
    )

    steps = 0
    while state.status != "completed" and steps < max_steps:
        if manual_player is not None and manual_token is not None:
            _prompt_and_submit_manual_action(
                client=client,
                game_id=created.game_id,
                player_id=manual_player,
                manual_token=manual_token,
                output_format=output_format,
            )
        if poll_interval:
            time.sleep(poll_interval)
        state = client.advance_game(created.game_id).state
        steps += 1

        timeline_batch = client.get_timeline(created.game_id, after=last_sequence)
        emitted_items.extend(timeline_batch.items)
        last_sequence = consume_timeline(
            timeline_batch.items,
            next_after=timeline_batch.next_after,
            log_jsonl=log_jsonl,
            show_items=show_timeline and output_format != "json",
            output_format=output_format,
        )

    if state.status != "completed":
        raise AppError(
            message_game_did_not_complete(max_steps),
            code=ErrorCode.CONFIG_INVALID_VALUE,
        )

    winner = state.winner or "unknown"
    logger.info(
        LOG_CLI_PLAY_COMPLETED,
        extra={
            "event_action": LOG_CLI_PLAY_COMPLETED,
            "event_outcome": "success",
            "game_id": created.game_id,
            "winner": winner,
            "steps": steps,
        },
    )
    if output_format == "table":
        print_state(state)
        console.print(f"[bold green]Game completed[/bold green]: winner={winner}, steps={steps}")
    elif output_format == "json":
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
    game_id: Annotated[str, typer.Argument(help="Game id to inspect.")],
    api_url: Annotated[str | None, typer.Option(help="Base URL for the API.")] = None,
    after: Annotated[int, typer.Option(help="Start after this timeline sequence.")] = 0,
    limit: Annotated[int | None, typer.Option(help="Maximum items per poll.")] = None,
    poll_interval: Annotated[
        float | None,
        typer.Option(help="Seconds to wait between polls when following."),
    ] = None,
    follow: Annotated[
        bool,
        typer.Option("--follow/--no-follow", help="Keep polling for new items."),
    ] = False,
    log_jsonl: Annotated[Path | None, typer.Option(help="Optional public timeline JSONL.")] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Output format: table, json, or jsonl."),
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
            client=_client(api_url),
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
    client: GameApiClient,
    output_format: OutputFormat,
) -> None:
    if follow and output_format == "json":
        raise AppError(MESSAGE_JSON_OUTPUT_CANNOT_FOLLOW, code=ErrorCode.CONFIG_INVALID_VALUE)
    if poll_interval < 0:
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
                "event_outcome": "success",
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
        typer.Option("--timeline", help="Public timeline JSONL."),
    ] = None,
    game_id: Annotated[
        str | None,
        typer.Option("--game-id", help="Game id to replay from the API."),
    ] = None,
    api_url: Annotated[str | None, typer.Option(help="Base URL for the API.")] = None,
    delay: Annotated[float, typer.Option(help="Seconds to wait between items.")] = 0.0,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Output format: table, json, or jsonl."),
    ] = None,
) -> None:
    """Replay public timeline items from JSONL or the public HTTP API."""
    run_app_command(
        lambda: _replay(
            timeline_file=timeline_file,
            game_id=game_id,
            delay=delay,
            client=_client(api_url),
            output_format=_output_format(output, get_settings()),
        )
    )


def _replay(
    *,
    timeline_file: Path | None,
    game_id: str | None,
    delay: float,
    client: GameApiClient,
    output_format: OutputFormat,
) -> None:
    if delay < 0:
        raise AppError(
            MESSAGE_POLL_INTERVAL_MUST_BE_NON_NEGATIVE,
            code=ErrorCode.CONFIG_INVALID_VALUE,
        )
    replay_items = _load_replay_items(timeline_file, game_id=game_id, client=client)
    if output_format == "json":
        for _ in replay_items:
            if delay:
                time.sleep(delay)
        print_timeline(replay_items, output_format=output_format)
        logger.info(
            LOG_CLI_REPLAY_COMPLETED,
            extra={
                "event_action": LOG_CLI_REPLAY_COMPLETED,
                "event_outcome": "success",
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
            "event_outcome": "success",
            "event_count": len(replay_items),
        },
    )


def games(
    api_url: Annotated[str | None, typer.Option(help="Base URL for the API.")] = None,
    status: Annotated[str | None, typer.Option(help="Optional game status filter.")] = None,
    limit: Annotated[int, typer.Option(help="Maximum games to return.")] = 20,
    offset: Annotated[int, typer.Option(help="Game page offset.")] = 0,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Output format: table, json, or jsonl."),
    ] = None,
) -> None:
    """List public game summaries."""
    run_app_command(
        lambda: _games(
            status=status,
            limit=limit,
            offset=offset,
            client=_client(api_url),
            output_format=_output_format(output, get_settings()),
        )
    )


def _games(
    *,
    status: str | None,
    limit: int,
    offset: int,
    client: GameApiClient,
    output_format: OutputFormat,
) -> None:
    response = client.list_games(status=status, limit=limit, offset=offset)
    print_game_summaries(response.games, output_format=output_format)
    if response.next_offset is not None and output_format == "table":
        console.print(f"[dim]next offset: {response.next_offset}[/dim]")


def _client(api_url: str | None) -> GameApiClient:
    settings = get_settings()
    return _build_game_api_client(api_url or settings.cli_api_url)


def _build_game_api_client(api_url: str, *, settings: AppSettings | None = None) -> GameApiClient:
    resolved_settings = settings or get_settings()
    return build_game_api_client(api_url, timeout=resolved_settings.cli_http_timeout_seconds)


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
    client: GameApiClient,
    game_id: str,
    player_id: str,
    manual_token: str,
    output_format: OutputFormat,
) -> None:
    observation = client.get_private_observation(
        game_id,
        player_id,
        manual_token=manual_token,
    )
    actions = observation.observation.get("available_actions") or []
    if not actions:
        return
    if output_format == "table":
        print_observation(observation)
    action_type = str(actions[0])
    target_id = None
    message = None
    if action_type == "speech":
        message = typer.prompt("speech")
    elif action_type != "pass":
        target_id = typer.prompt(f"{action_type} target_id")
    response = client.submit_player_action(
        game_id,
        player_id,
        PlayerActionRequest(
            type=cast(Any, action_type),
            target_id=target_id,
            message=message,
        ),
        manual_token=manual_token,
    )
    logger.info(
        LOG_CLI_ACTION_SUBMITTED,
        extra={
            "event_action": LOG_CLI_ACTION_SUBMITTED,
            "event_outcome": "success",
            "game_id": game_id,
            "has_target": target_id is not None,
            "has_message": bool(message),
        },
    )
    if output_format == "table":
        print_timeline(response.timeline)


def _load_replay_items(
    timeline_file: Path | None,
    *,
    game_id: str | None,
    client: GameApiClient,
) -> list[GameTimelineItem]:
    if timeline_file is not None:
        return [
            GameTimelineItem.model_validate_json(line)
            for line in timeline_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if game_id is not None:
        return client.get_timeline(game_id, after=0, limit=500).items
    raise AppError(
        "Either --timeline or --game-id is required.",
        code=ErrorCode.CONFIG_INVALID_VALUE,
    )


def _output_format(value: str | None, settings: AppSettings) -> OutputFormat:
    raw_value = value or settings.cli_output_format
    if raw_value not in {"table", "json", "jsonl"}:
        raise AppError(MESSAGE_OUTPUT_FORMAT_MUST_BE_VALID, code=ErrorCode.CONFIG_INVALID_VALUE)
    return cast(OutputFormat, raw_value)
