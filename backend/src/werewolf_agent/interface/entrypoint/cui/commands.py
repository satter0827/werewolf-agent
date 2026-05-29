"""Typer command handlers for local development workflows."""

from __future__ import annotations

import logging
import platform
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Any, cast
from urllib.parse import urlsplit, urlunsplit

import typer
from rich.panel import Panel
from rich.table import Table

from werewolf_agent.commons.configuration import (
    APP_NAME,
    AppSettings,
    get_settings,
    repository_root,
)
from werewolf_agent.commons.shared.constants import REDACTED
from werewolf_agent.commons.shared.messages import (
    LOG_CLI_ACTION_SUBMITTED,
    LOG_CLI_GAME_CREATED,
    LOG_CLI_PLAY_COMPLETED,
    LOG_CLI_REPLAY_COMPLETED,
    LOG_CLI_WATCH_POLLED,
    MESSAGE_JSON_OUTPUT_CANNOT_FOLLOW,
    MESSAGE_MAX_STEPS_MUST_BE_AT_LEAST_ONE,
    MESSAGE_OUTPUT_FORMAT_MUST_BE_VALID,
    MESSAGE_POLL_INTERVAL_MUST_BE_NON_NEGATIVE,
    message_game_did_not_complete,
)
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    PublicGameEvent,
    SubmitPlayerActionRequest,
)
from werewolf_agent.interface.entrypoint.cui.errors import run_app_command
from werewolf_agent.interface.entrypoint.cui.output import (
    OutputFormat,
    console,
    consume_events,
    print_events,
    print_json,
    print_observation,
    print_ruleset,
    print_run_summaries,
    print_state,
    print_turns,
)
from werewolf_agent.interface.entrypoint.shared import (
    GameApiClient,
    HttpGameApiClient,
    build_create_game_request,
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
    root = repository_root()
    settings = get_settings()
    resolved_api_url = api_url or settings.cli_api_url
    output_format = _output_format(output, settings)
    checks: dict[str, str] = {
        "package": f"{APP_NAME} {_package_version()}",
        "python": sys.version.split()[0],
        "python executable": sys.executable,
        "platform": platform.platform(),
        "repository": str(root),
        "env file": _env_file_status(root),
        "api url": resolved_api_url,
        "provider": settings.llm_provider,
        "model": settings.model,
        "prompt file": str(settings.llm_prompt_path or "packaged"),
        "fake responses file": str(settings.llm_fake_responses_path or "packaged"),
        "log level": settings.log_level,
        "log output": settings.log_output,
        "log dir": str(settings.log_directory_path),
        "log file": str(settings.log_file_path),
        "log retention days": str(settings.log_retention_days),
        "log third party level": settings.log_third_party_level,
        "database": _redacted_database_url(settings.sqlalchemy_database_url),
    }
    try:
        health = _build_game_api_client(resolved_api_url).health()
    except AppError as exc:
        checks["api health"] = exc.detail
    else:
        checks["api health"] = health.get("status", "ok")

    if output_format != "table":
        print_json(checks, output_format=output_format)
        return

    table = Table(title="Werewolf Agent Doctor")
    table.add_column("Check", style="cyan", no_wrap=True)
    table.add_column("Value", overflow="fold")
    for key, value in checks.items():
        table.add_row(key, value)
    console.print(table)


def ruleset(
    api_url: Annotated[
        str | None,
        typer.Option(help="Base URL for the Werewolf Agent API."),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Output format: table, json, or jsonl."),
    ] = None,
) -> None:
    """Print default ruleset metadata."""
    run_app_command(
        lambda: _ruleset(
            client=_client(api_url),
            output_format=_output_format(output, get_settings()),
        )
    )


def _ruleset(*, client: GameApiClient, output_format: OutputFormat) -> None:
    print_ruleset(client.get_ruleset(), output_format=output_format)


def create(
    api_url: Annotated[str | None, typer.Option(help="Base URL for the API.")] = None,
    players: Annotated[int | None, typer.Option("--players", help="Number of players.")] = None,
    seed: Annotated[int | None, typer.Option(help="Deterministic seed.")] = None,
    human_player: Annotated[
        str | None,
        typer.Option("--human-player", help="Player id controlled by this CLI."),
    ] = None,
    role_count: Annotated[
        list[str] | None,
        typer.Option("--role-count", help="Role count entry, e.g. werewolf=1."),
    ] = None,
    tie_break_policy: Annotated[
        str,
        typer.Option(help="Tie break policy: no_elimination or random_elimination."),
    ] = "no_elimination",
    day_speech_turns: Annotated[int, typer.Option(help="Speech turns per day.")] = 1,
    allow_self_vote: Annotated[
        bool,
        typer.Option("--allow-self-vote/--no-allow-self-vote", help="Allow self voting."),
    ] = False,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Output format: table, json, or jsonl."),
    ] = None,
) -> None:
    """Create one game through the public HTTP API."""
    run_app_command(
        lambda: _create(
            players=players,
            seed=seed,
            human_player=human_player,
            role_count=role_count or [],
            tie_break_policy=tie_break_policy,
            day_speech_turns=day_speech_turns,
            allow_self_vote=allow_self_vote,
            client=_client(api_url),
            output_format=_output_format(output, get_settings()),
        )
    )


def _create(
    *,
    players: int | None,
    seed: int | None,
    human_player: str | None,
    role_count: list[str],
    tie_break_policy: str,
    day_speech_turns: int,
    allow_self_vote: bool,
    client: GameApiClient,
    output_format: OutputFormat,
) -> None:
    request = build_create_game_request(
        players=players,
        seed=seed,
        human_player=human_player,
        role_count=role_count,
        tie_break_policy=tie_break_policy,
        day_speech_turns=day_speech_turns,
        allow_self_vote=allow_self_vote,
        default_player_count=get_settings().game_default_player_count,
    )
    created = client.create_game(request)
    logger.info(
        LOG_CLI_GAME_CREATED,
        extra={"game_id": created.game_id, "human_player": human_player},
    )
    if output_format != "table":
        print_json(created, output_format=output_format)
        return
    console.print(Panel.fit(f"Created game [bold]{created.game_id}[/bold]"))
    print_state(created.state)
    if created.control_tokens:
        for player_id, control_token in created.control_tokens.items():
            console.print(f"[yellow]control token[/yellow] {player_id}: {control_token}")


def state(
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


def step(
    game_id: Annotated[str, typer.Argument(help="Game id to advance.")],
    api_url: Annotated[str | None, typer.Option(help="Base URL for the API.")] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Output format: table, json, or jsonl."),
    ] = None,
) -> None:
    """Advance one game by one API step."""
    run_app_command(
        lambda: _step(
            game_id=game_id,
            client=_client(api_url),
            output_format=_output_format(output, get_settings()),
        )
    )


def _step(*, game_id: str, client: GameApiClient, output_format: OutputFormat) -> None:
    response = client.step_game(game_id)
    if output_format != "table":
        print_json(response, output_format=output_format)
        return
    print_state(response.state)
    print_events(response.events)


def play(
    api_url: Annotated[str | None, typer.Option(help="Base URL for the API.")] = None,
    players: Annotated[int | None, typer.Option("--players", help="Number of players.")] = None,
    seed: Annotated[int | None, typer.Option(help="Deterministic seed.")] = None,
    human_player: Annotated[
        str | None,
        typer.Option("--human-player", help="Player id controlled by this CLI."),
    ] = None,
    max_steps: Annotated[int | None, typer.Option(help="Maximum API step calls.")] = None,
    log_jsonl: Annotated[Path | None, typer.Option(help="Optional public event JSONL.")] = None,
    poll_interval: Annotated[
        float | None,
        typer.Option(help="Seconds to wait between API step calls."),
    ] = None,
    show_events: Annotated[
        bool,
        typer.Option("--show-events/--no-show-events", help="Print public events."),
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
            players=players,
            seed=seed,
            human_player=human_player,
            max_steps=max_steps or settings.cli_max_steps,
            log_jsonl=log_jsonl,
            poll_interval=(
                settings.cli_poll_interval_seconds if poll_interval is None else poll_interval
            ),
            show_events=show_events,
            client=_client(api_url),
            output_format=_output_format(output, settings),
        )
    )


def _play(
    *,
    players: int | None,
    seed: int | None,
    human_player: str | None,
    max_steps: int,
    log_jsonl: Path | None,
    poll_interval: float,
    show_events: bool,
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

    request = build_create_game_request(
        players=players,
        seed=seed,
        human_player=human_player,
        role_count=[],
        tie_break_policy="no_elimination",
        day_speech_turns=1,
        allow_self_vote=False,
        default_player_count=get_settings().game_default_player_count,
    )
    created = client.create_game(request)
    state = created.state
    last_sequence = 0
    emitted_events: list[PublicGameEvent] = []
    control_token = (
        created.control_tokens.get(human_player)
        if created.control_tokens is not None and human_player is not None
        else None
    )

    if output_format == "table":
        console.print(Panel.fit(f"Created game [bold]{created.game_id}[/bold]"))
        print_state(state)

    initial_events = client.list_events(created.game_id, after=last_sequence)
    emitted_events.extend(initial_events.events)
    last_sequence = consume_events(
        initial_events.events,
        next_after=initial_events.next_after,
        log_jsonl=log_jsonl,
        show_events=show_events and output_format != "json",
        output_format=output_format,
    )

    steps = 0
    while state.status != "completed" and steps < max_steps:
        if human_player is not None and control_token is not None:
            _prompt_and_submit_human_action(
                client=client,
                game_id=created.game_id,
                player_id=human_player,
                control_token=control_token,
                output_format=output_format,
            )
        if poll_interval:
            time.sleep(poll_interval)
        stepped = client.step_game(created.game_id)
        state = stepped.state
        steps += 1

        event_batch = client.list_events(created.game_id, after=last_sequence)
        emitted_events.extend(event_batch.events)
        last_sequence = consume_events(
            event_batch.events,
            next_after=event_batch.next_after,
            log_jsonl=log_jsonl,
            show_events=show_events and output_format != "json",
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
        extra={"game_id": created.game_id, "winner": winner, "steps": steps},
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
                "events": emitted_events if show_events else [],
            },
            output_format=output_format,
        )
    else:
        print_json(
            {"game_id": created.game_id, "winner": winner, "steps": steps},
            output_format=output_format,
        )


def watch(
    game_id: Annotated[str, typer.Argument(help="Game id to watch.")],
    api_url: Annotated[str | None, typer.Option(help="Base URL for the API.")] = None,
    after: Annotated[int, typer.Option(help="Start after this event sequence.")] = 0,
    limit: Annotated[int | None, typer.Option(help="Maximum events per poll.")] = None,
    poll_interval: Annotated[
        float | None,
        typer.Option(help="Seconds to wait between polls when following."),
    ] = None,
    follow: Annotated[
        bool,
        typer.Option("--follow/--no-follow", help="Keep polling for new events."),
    ] = False,
    log_jsonl: Annotated[Path | None, typer.Option(help="Optional public event JSONL.")] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Output format: table, json, or jsonl."),
    ] = None,
) -> None:
    """Watch public game events through the public HTTP API."""
    settings = get_settings()
    run_app_command(
        lambda: _watch(
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


def _watch(
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
        batch = client.list_events(game_id, after=last_sequence, limit=limit)
        last_sequence = consume_events(
            batch.events,
            next_after=batch.next_after,
            log_jsonl=log_jsonl,
            show_events=True,
            output_format=output_format,
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
    events: Annotated[Path | None, typer.Option("--events", help="Public event JSONL.")] = None,
    game_id: Annotated[
        str | None,
        typer.Option("--game-id", help="Game id to replay from the API."),
    ] = None,
    api_url: Annotated[str | None, typer.Option(help="Base URL for the API.")] = None,
    delay: Annotated[float, typer.Option(help="Seconds to wait between events.")] = 0.0,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Output format: table, json, or jsonl."),
    ] = None,
) -> None:
    """Replay public events from JSONL or the public HTTP API."""
    run_app_command(
        lambda: _replay(
            events=events,
            game_id=game_id,
            delay=delay,
            client=_client(api_url),
            output_format=_output_format(output, get_settings()),
        )
    )


def _replay(
    *,
    events: Path | None,
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
    replay_events = _load_replay_events(events, game_id=game_id, client=client)
    if output_format == "json":
        for _ in replay_events:
            if delay:
                time.sleep(delay)
        print_events(replay_events, output_format=output_format)
        logger.info(LOG_CLI_REPLAY_COMPLETED, extra={"event_count": len(replay_events)})
        return
    for event in replay_events:
        if delay:
            time.sleep(delay)
        print_events([event], output_format=output_format)
    logger.info(LOG_CLI_REPLAY_COMPLETED, extra={"event_count": len(replay_events)})


def runs(
    api_url: Annotated[str | None, typer.Option(help="Base URL for the API.")] = None,
    status: Annotated[str | None, typer.Option(help="Optional run status filter.")] = None,
    limit: Annotated[int, typer.Option(help="Maximum runs to return.")] = 20,
    offset: Annotated[int, typer.Option(help="Run page offset.")] = 0,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Output format: table, json, or jsonl."),
    ] = None,
) -> None:
    """List public game run summaries."""
    run_app_command(
        lambda: _runs(
            status=status,
            limit=limit,
            offset=offset,
            client=_client(api_url),
            output_format=_output_format(output, get_settings()),
        )
    )


def _runs(
    *,
    status: str | None,
    limit: int,
    offset: int,
    client: GameApiClient,
    output_format: OutputFormat,
) -> None:
    response = client.list_games(status=status, limit=limit, offset=offset)
    print_run_summaries(response.runs, output_format=output_format)
    if response.next_offset is not None and output_format == "table":
        console.print(f"[dim]next offset: {response.next_offset}[/dim]")


def turns(
    game_id: Annotated[str, typer.Argument(help="Game id to inspect.")],
    api_url: Annotated[str | None, typer.Option(help="Base URL for the API.")] = None,
    after: Annotated[int, typer.Option(help="Start after this turn sequence.")] = 0,
    limit: Annotated[int | None, typer.Option(help="Maximum turns to return.")] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Output format: table, json, or jsonl."),
    ] = None,
) -> None:
    """List public turn history for one game."""
    settings = get_settings()
    run_app_command(
        lambda: _turns(
            game_id=game_id,
            after=after,
            limit=limit or settings.cli_event_limit,
            client=_client(api_url),
            output_format=_output_format(output, settings),
        )
    )


def _turns(
    *,
    game_id: str,
    after: int,
    limit: int,
    client: GameApiClient,
    output_format: OutputFormat,
) -> None:
    response = client.list_turns(game_id, after=after, limit=limit)
    print_turns(response.turns, output_format=output_format)
    if response.next_after != after and output_format == "table":
        console.print(f"[dim]next after: {response.next_after}[/dim]")


def _client(api_url: str | None) -> GameApiClient:
    settings = get_settings()
    return _build_game_api_client(api_url or settings.cli_api_url)


def _build_game_api_client(api_url: str, *, settings: AppSettings | None = None) -> GameApiClient:
    resolved_settings = settings or get_settings()
    return HttpGameApiClient(api_url, timeout=resolved_settings.cli_http_timeout_seconds)


def _prompt_and_submit_human_action(
    *,
    client: GameApiClient,
    game_id: str,
    player_id: str,
    control_token: str,
    output_format: OutputFormat,
) -> None:
    observation = client.get_private_observation(
        game_id,
        player_id,
        control_token=control_token,
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
        SubmitPlayerActionRequest(
            type=cast(Any, action_type),
            target_id=target_id,
            message=message,
        ),
        control_token=control_token,
    )
    logger.info(
        LOG_CLI_ACTION_SUBMITTED,
        extra={"game_id": game_id, "player_id": player_id, "action_type": action_type},
    )
    if output_format == "table":
        print_events(response.events)


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


def _output_format(value: str | None, settings: AppSettings) -> OutputFormat:
    raw_value = value or settings.cli_output_format
    if raw_value not in {"table", "json", "jsonl"}:
        raise AppError(MESSAGE_OUTPUT_FORMAT_MUST_BE_VALID, code=ErrorCode.CONFIG_INVALID_VALUE)
    return cast(OutputFormat, raw_value)


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
