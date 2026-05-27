"""Typer command handlers for local development workflows."""

from __future__ import annotations

import platform
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from werewolf_agent.contracts import AppError, ErrorCode
from werewolf_agent.interface.cui.client import GameApiClient, HttpGameApiClient
from werewolf_agent.interface.cui.errors import run_app_command
from werewolf_agent.interface.cui.output import console, consume_events, print_state
from werewolf_agent.interface.shared.schemas import CreateGameRequest
from werewolf_agent.interface.shared.settings import APP_NAME, get_settings, repository_root


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
    table.add_row("log level", settings.log_level)
    table.add_row("log format", settings.log_format)
    table.add_row("log output", settings.log_output)
    table.add_row("database", settings.sqlalchemy_database_url)

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
        typer.Option(help="Deterministic seed for role assignment and dummy flow."),
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
        raise AppError("max_steps must be at least 1.", code=ErrorCode.CONFIG_INVALID_VALUE)
    if poll_interval < 0:
        raise AppError(
            "poll_interval must be zero or greater.",
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
            f"Game did not complete within {max_steps} API steps.",
            code=ErrorCode.CONFIG_INVALID_VALUE,
        )

    print_state(state)
    winner = state.winner or "unknown"
    console.print(f"[bold green]Game completed[/bold green]: winner={winner}, steps={steps}")


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
