"""Typer command handlers for local development workflows."""

from __future__ import annotations

import logging
import platform
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit, urlunsplit

import typer
from rich.panel import Panel
from rich.table import Table

from werewolf_agent.commons.shared.codes import ErrorCode
from werewolf_agent.commons.shared.constants import REDACTED
from werewolf_agent.commons.shared.messages import (
    LOG_CLI_PLAY_COMPLETED,
    LOG_CLI_REPLAY_COMPLETED,
    LOG_CLI_WATCH_POLLED,
    MESSAGE_MAX_STEPS_MUST_BE_AT_LEAST_ONE,
    MESSAGE_POLL_INTERVAL_MUST_BE_NON_NEGATIVE,
    message_game_did_not_complete,
)
from werewolf_agent.contracts import AppError
from werewolf_agent.interface.entrypoint.cui.client import GameApiClient, HttpGameApiClient
from werewolf_agent.interface.entrypoint.cui.errors import run_app_command
from werewolf_agent.interface.entrypoint.cui.output import (
    console,
    consume_events,
    print_run_summaries,
    print_state,
    print_turns,
)
from werewolf_agent.interface.shared.schemas import CreateGameRequest, PublicGameEvent
from werewolf_agent.interface.shared.settings import APP_NAME, get_settings, repository_root

logger = logging.getLogger(__name__)


def doctor() -> None:
    """Print local development environment diagnostics."""
    run_app_command(_doctor)


def _doctor() -> None:
    root = repository_root()
    settings = get_settings()

    table = Table(title="Werewolf Agent Doctor")
    table.add_column("Check", style="cyan", no_wrap=True)
    table.add_column("Value", overflow="fold")
    table.add_row("package", f"{APP_NAME} {_package_version()}")
    table.add_row("python", sys.version.split()[0])
    table.add_row("python executable", sys.executable)
    table.add_row("platform", platform.platform())
    table.add_row("repository", str(root))
    table.add_row("env file", _env_file_status(root))
    table.add_row("provider", settings.llm_provider)
    table.add_row("model", settings.model)
    table.add_row("fake llm strategy", settings.fake_llm_strategy)
    table.add_row("log level", settings.log_level)
    table.add_row("log format", settings.log_format)
    table.add_row("log output", settings.log_output)
    table.add_row("database", _redacted_database_url(settings.sqlalchemy_database_url))

    console.print(table)


def play(
    api_url: Annotated[
        str,
        typer.Option(help="Base URL for the already-running Werewolf Agent API."),
    ] = "http://127.0.0.1:8000/api/v1",
    players: Annotated[
        int,
        typer.Option("--players", help="Number of players for the game."),
    ] = 6,
    seed: Annotated[
        int | None,
        typer.Option(help="Deterministic seed for role assignment and FakeLLM flow."),
    ] = None,
    max_steps: Annotated[
        int,
        typer.Option(help="Maximum API step calls before the CUI stops."),
    ] = 64,
    log_jsonl: Annotated[
        Path | None,
        typer.Option(help="Optional JSONL file for public API events."),
    ] = None,
    poll_interval: Annotated[
        float,
        typer.Option(help="Seconds to wait between API step calls."),
    ] = 0.0,
    show_events: Annotated[
        bool,
        typer.Option("--show-events/--no-show-events", help="Print public events as they arrive."),
    ] = True,
) -> None:
    """Run one game through the public HTTP API."""
    run_app_command(
        lambda: _play(
            api_url=api_url,
            players=players,
            seed=seed,
            max_steps=max_steps,
            log_jsonl=log_jsonl,
            poll_interval=poll_interval,
            show_events=show_events,
            client=_build_game_api_client(api_url),
        )
    )


def _build_game_api_client(api_url: str) -> GameApiClient:
    return HttpGameApiClient(api_url)


def _play(
    *,
    api_url: str,
    players: int,
    seed: int | None,
    max_steps: int,
    log_jsonl: Path | None,
    poll_interval: float,
    show_events: bool,
    client: GameApiClient,
) -> None:
    if max_steps < 1:
        raise AppError(MESSAGE_MAX_STEPS_MUST_BE_AT_LEAST_ONE, code=ErrorCode.CONFIG_INVALID_VALUE)
    if poll_interval < 0:
        raise AppError(
            MESSAGE_POLL_INTERVAL_MUST_BE_NON_NEGATIVE,
            code=ErrorCode.CONFIG_INVALID_VALUE,
        )

    request = CreateGameRequest(player_count=players, seed=seed)
    created = client.create_game(request)
    state = created.state
    last_sequence = 0

    console.print(Panel.fit(f"Created game [bold]{created.game_id}[/bold] via {api_url}"))
    print_state(state)

    initial_events = client.list_events(created.game_id, after=last_sequence)
    last_sequence = consume_events(
        initial_events.events,
        next_after=initial_events.next_after,
        log_jsonl=log_jsonl,
        show_events=show_events,
    )

    steps = 0
    while state.status != "completed" and steps < max_steps:
        if poll_interval:
            time.sleep(poll_interval)
        stepped = client.step_game(created.game_id)
        state = stepped.state
        steps += 1

        event_batch = client.list_events(created.game_id, after=last_sequence)
        last_sequence = consume_events(
            event_batch.events,
            next_after=event_batch.next_after,
            log_jsonl=log_jsonl,
            show_events=show_events,
        )

    if state.status != "completed":
        raise AppError(
            message_game_did_not_complete(max_steps),
            code=ErrorCode.CONFIG_INVALID_VALUE,
        )

    print_state(state)
    winner = state.winner or "unknown"
    logger.info(
        LOG_CLI_PLAY_COMPLETED,
        extra={"game_id": created.game_id, "winner": winner, "steps": steps},
    )
    console.print(f"[bold green]Game completed[/bold green]: winner={winner}, steps={steps}")


def watch(
    game_id: Annotated[str, typer.Argument(help="Game id to watch.")],
    api_url: Annotated[
        str,
        typer.Option(help="Base URL for the already-running Werewolf Agent API."),
    ] = "http://127.0.0.1:8000/api/v1",
    after: Annotated[int, typer.Option(help="Start after this event sequence.")] = 0,
    limit: Annotated[int, typer.Option(help="Maximum events per poll.")] = 100,
    poll_interval: Annotated[
        float,
        typer.Option(help="Seconds to wait between polls when following."),
    ] = 1.0,
    follow: Annotated[
        bool,
        typer.Option("--follow/--no-follow", help="Keep polling for new events."),
    ] = False,
    log_jsonl: Annotated[
        Path | None,
        typer.Option(help="Optional JSONL file for public API events."),
    ] = None,
) -> None:
    """Watch public game events through the public HTTP API."""
    run_app_command(
        lambda: _watch(
            game_id=game_id,
            after=after,
            limit=limit,
            poll_interval=poll_interval,
            follow=follow,
            log_jsonl=log_jsonl,
            client=_build_game_api_client(api_url),
        )
    )


def _watch(
    *,
    game_id: str,
    after: int,
    limit: int,
    poll_interval: float,
    follow: bool,
    log_jsonl: Path | None,
    client: GameApiClient,
) -> None:
    if poll_interval < 0:
        raise AppError(
            MESSAGE_POLL_INTERVAL_MUST_BE_NON_NEGATIVE,
            code=ErrorCode.CONFIG_INVALID_VALUE,
        )

    last_sequence = after
    while True:
        previous_sequence = last_sequence
        batch = client.list_events(game_id, after=last_sequence, limit=limit)
        last_sequence = consume_events(
            batch.events,
            next_after=batch.next_after,
            log_jsonl=log_jsonl,
            show_events=True,
        )
        logger.debug(
            LOG_CLI_WATCH_POLLED,
            extra={
                "game_id": game_id,
                "after": previous_sequence,
                "next_after": last_sequence,
                "event_count": len(batch.events),
            },
        )
        if not follow:
            return
        time.sleep(poll_interval)


def replay(
    events: Annotated[
        Path | None,
        typer.Option("--events", help="Public event JSONL archive to replay."),
    ] = None,
    game_id: Annotated[
        str | None,
        typer.Option("--game-id", help="Game id to replay from the API."),
    ] = None,
    api_url: Annotated[
        str,
        typer.Option(help="Base URL for the already-running Werewolf Agent API."),
    ] = "http://127.0.0.1:8000/api/v1",
    delay: Annotated[float, typer.Option(help="Seconds to wait between events.")] = 0.0,
) -> None:
    """Replay public events from JSONL or the public HTTP API."""
    run_app_command(
        lambda: _replay(
            events=events,
            game_id=game_id,
            delay=delay,
            client=_build_game_api_client(api_url),
        )
    )


def _replay(
    *,
    events: Path | None,
    game_id: str | None,
    delay: float,
    client: GameApiClient,
) -> None:
    if delay < 0:
        raise AppError(
            MESSAGE_POLL_INTERVAL_MUST_BE_NON_NEGATIVE,
            code=ErrorCode.CONFIG_INVALID_VALUE,
        )
    replay_events = _load_replay_events(events, game_id=game_id, client=client)
    for event in replay_events:
        if delay:
            time.sleep(delay)
        console.print(
            f"[dim]{event.sequence}[/dim] [bold]{event.event_type}[/bold] {event.payload}"
        )
    logger.info(LOG_CLI_REPLAY_COMPLETED, extra={"event_count": len(replay_events)})


def runs(
    api_url: Annotated[
        str,
        typer.Option(help="Base URL for the already-running Werewolf Agent API."),
    ] = "http://127.0.0.1:8000/api/v1",
    status: Annotated[
        str | None,
        typer.Option(help="Optional run status filter."),
    ] = None,
    limit: Annotated[int, typer.Option(help="Maximum runs to return.")] = 20,
    offset: Annotated[int, typer.Option(help="Run page offset.")] = 0,
) -> None:
    """List public game run summaries."""
    run_app_command(
        lambda: _runs(
            status=status,
            limit=limit,
            offset=offset,
            client=_build_game_api_client(api_url),
        )
    )


def _runs(
    *,
    status: str | None,
    limit: int,
    offset: int,
    client: GameApiClient,
) -> None:
    response = client.list_games(status=status, limit=limit, offset=offset)
    print_run_summaries(response.runs)
    if response.next_offset is not None:
        console.print(f"[dim]next offset: {response.next_offset}[/dim]")


def turns(
    game_id: Annotated[str, typer.Argument(help="Game id to inspect.")],
    api_url: Annotated[
        str,
        typer.Option(help="Base URL for the already-running Werewolf Agent API."),
    ] = "http://127.0.0.1:8000/api/v1",
    after: Annotated[int, typer.Option(help="Start after this turn sequence.")] = 0,
    limit: Annotated[int, typer.Option(help="Maximum turns to return.")] = 100,
) -> None:
    """List public turn history for one game."""
    run_app_command(
        lambda: _turns(
            game_id=game_id,
            after=after,
            limit=limit,
            client=_build_game_api_client(api_url),
        )
    )


def _turns(
    *,
    game_id: str,
    after: int,
    limit: int,
    client: GameApiClient,
) -> None:
    response = client.list_turns(game_id, after=after, limit=limit)
    print_turns(response.turns)
    if response.next_after != after:
        console.print(f"[dim]next after: {response.next_after}[/dim]")


def _load_replay_events(
    events: Path | None,
    *,
    game_id: str | None,
    client: GameApiClient,
) -> list[PublicGameEvent]:
    if events is not None:
        return [
            PublicGameEvent.model_validate_json(line)
            for line in events.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if game_id is not None:
        return client.list_events(game_id, after=0, limit=500).events
    raise AppError(
        "Either --events or --game-id is required.",
        code=ErrorCode.CONFIG_INVALID_VALUE,
    )


def _package_version() -> str:
    try:
        return version(APP_NAME)
    except PackageNotFoundError:
        return "editable"


def _env_file_status(root: Path) -> str:
    env_path = root / ".env"
    example_path = root / ".env.example"

    if env_path.exists():
        return ".env found"
    if example_path.exists():
        return ".env missing; copy .env.example when enabling real providers"
    return ".env and .env.example missing"


def _redacted_database_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.password is None:
        return value

    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"

    user = parsed.username or ""
    credentials = f"{user}:{REDACTED}" if user else REDACTED
    return urlunsplit(
        (parsed.scheme, f"{credentials}@{host}", parsed.path, parsed.query, parsed.fragment)
    )
