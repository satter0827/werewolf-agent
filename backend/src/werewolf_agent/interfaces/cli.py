"""Command line interface for local development workflows."""

from __future__ import annotations

import json
import logging
import platform
import sys
import time
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, TypeVar

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from werewolf_agent.commons.logging import configure_logging
from werewolf_agent.config import APP_NAME, get_settings, repository_root
from werewolf_agent.contracts import AppError, ConfigError, ErrorCode
from werewolf_agent.interfaces.api.schemas import (
    CreateGameRequest,
    PublicGameEvent,
    PublicGameState,
)
from werewolf_agent.interfaces.api_client import GameApiClient, HttpGameApiClient

T = TypeVar("T")

logger = logging.getLogger(__name__)

app = typer.Typer(
    help="Werewolf Agent development and gameplay commands.",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def main() -> None:
    """Werewolf Agent command group."""
    try:
        configure_logging(get_settings())
    except ValidationError as exc:
        error = ConfigError(_settings_error_detail(exc))
        typer.echo(f"Error: {error.detail}", err=True)
        raise typer.Exit(code=1) from exc


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


def run_app_command(command: Callable[[], T]) -> T:
    """Run one CLI command body with shared application error handling."""
    try:
        return command()
    except AppError as exc:
        logger.error("Command failed", extra=exc.log_extra())
        typer.echo(f"Error: {exc.detail}", err=True)
        raise typer.Exit(code=1) from exc


def _settings_error_detail(error: ValidationError) -> str:
    issues = error.errors()
    if not issues:
        return "Invalid application configuration."

    first_issue = issues[0]
    location = _settings_error_location(first_issue.get("loc", ()))
    message = str(first_issue.get("msg", "Invalid value."))
    return f"Invalid configuration for {location}: {message}"


def _settings_error_location(location: object) -> str:
    if isinstance(location, (tuple, list)):
        parts = [str(part) for part in location]
    elif location in (None, ""):
        parts = []
    else:
        parts = [str(location)]
    return ".".join(parts) if parts else "settings"


@app.command()
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

    console.print(table)


@app.command()
def play(
    api_url: Annotated[
        str,
        typer.Option(help="Base URL for the already-running Werewolf Agent API."),
    ] = "http://127.0.0.1:8000/api",
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
        typer.Option(help="Maximum API step calls before the CLI stops."),
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
    _print_state(state)

    initial_events = client.list_events(created.game_id, after=last_sequence)
    last_sequence = _consume_events(
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
        last_sequence = _consume_events(
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

    _print_state(state)
    winner = state.winner or "unknown"
    console.print(f"[bold green]Game completed[/bold green]: winner={winner}, steps={steps}")


def _consume_events(
    events: list[PublicGameEvent],
    *,
    next_after: int,
    log_jsonl: Path | None,
    show_events: bool,
) -> int:
    if log_jsonl is not None:
        _append_events_jsonl(log_jsonl, events)
    if show_events:
        _print_events(events)
    return next_after


def _print_state(state: PublicGameState) -> None:
    table = Table(title="Game State")
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", overflow="fold")
    table.add_row("game", state.game_id)
    table.add_row("status", state.status)
    table.add_row("phase", state.phase)
    table.add_row("day", str(state.day))
    table.add_row("alive", ", ".join(state.alive_player_ids))
    table.add_row("eliminated", ", ".join(state.eliminated_player_ids) or "-")
    table.add_row("winner", state.winner or "-")
    console.print(table)


def _print_events(events: list[PublicGameEvent]) -> None:
    if not events:
        return

    table = Table(title="Public Events")
    table.add_column("Seq", justify="right", no_wrap=True)
    table.add_column("Phase", no_wrap=True)
    table.add_column("Event", no_wrap=True)
    table.add_column("Detail", overflow="fold")
    for event in events:
        table.add_row(
            str(event.sequence),
            f"{event.phase} day={event.day}",
            event.event_type,
            _event_detail(event),
        )
    console.print(table)


def _event_detail(event: PublicGameEvent) -> str:
    payload = event.payload
    if event.event_type == "speech_recorded":
        return str(payload.get("message", ""))
    if event.event_type == "vote_submitted":
        return f"{event.actor_id} -> {payload.get('target_id')}"
    if event.event_type == "vote_resolved":
        return f"eliminated={payload.get('eliminated_player_id')}"
    if event.event_type == "game_finished":
        return f"winner={payload.get('winner')}"
    if "message" in payload:
        return str(payload["message"])
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _append_events_jsonl(path: Path, events: list[PublicGameEvent]) -> None:
    if not events:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as output:
        for event in events:
            output.write(event.model_dump_json(exclude_none=True))
            output.write("\n")


if __name__ == "__main__":
    app()
