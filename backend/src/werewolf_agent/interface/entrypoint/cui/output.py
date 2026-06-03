"""Rich output helpers for the command line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from werewolf_agent.contracts.schemas import (
    GameSetupOptionsResponse,
    GameTimelineItem,
    PlayerObservationResponse,
    PublicGameState,
    PublicGameSummary,
)

console = Console()
OutputFormat = Literal["table", "json", "jsonl"]


def print_health(payload: dict[str, str], *, output_format: OutputFormat = "table") -> None:
    """Print API health."""
    if output_format != "table":
        print_json(payload, output_format=output_format)
        return

    table = Table(title="API Health")
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", overflow="fold")
    for key, value in payload.items():
        table.add_row(key, value)
    console.print(table)


def print_setup_options(
    options: GameSetupOptionsResponse,
    *,
    output_format: OutputFormat = "table",
) -> None:
    """Print public setup metadata."""
    if output_format != "table":
        print_json(options, output_format=output_format)
        return

    table = Table(title="Game Setup")
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", overflow="fold")
    table.add_row("player count", str(options.player_count))
    table.add_row("roles", ", ".join(role.id for role in options.roles))
    table.add_row("default role counts", str(options.default_role_counts))
    console.print(table)


def print_state(state: PublicGameState, *, output_format: OutputFormat = "table") -> None:
    """Print a compact public game state table."""
    if output_format != "table":
        print_json(state, output_format=output_format)
        return

    table = Table(title=f"Game {state.game_id}")
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", overflow="fold")
    table.add_row("status", state.status)
    table.add_row("phase", state.phase)
    table.add_row("day", str(state.day))
    table.add_row("version", str(state.version))
    table.add_row("alive", ", ".join(state.alive_player_ids) or "-")
    table.add_row("eliminated", ", ".join(state.eliminated_player_ids) or "-")
    table.add_row("winner", state.winner or "-")
    console.print(table)


def print_observation(
    response: PlayerObservationResponse,
    *,
    output_format: OutputFormat = "table",
) -> None:
    """Print one private observation."""
    if output_format != "table":
        print_json(response, output_format=output_format)
        return

    observation = response.observation
    raw_me = observation.get("me")
    me = raw_me if isinstance(raw_me, dict) else {}
    table = Table(title=f"Observation {response.player_id}")
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", overflow="fold")
    table.add_row("phase", str(observation.get("phase", "-")))
    table.add_row("day", str(observation.get("day", "-")))
    table.add_row("role", str(me.get("role", "-")))
    table.add_row("available actions", ", ".join(observation.get("available_actions") or []) or "-")
    table.add_row("known roles", str(observation.get("known_roles") or {}))
    console.print(table)


def consume_timeline(
    items: list[GameTimelineItem],
    *,
    next_after: int,
    log_jsonl: Path | None,
    show_items: bool,
    output_format: OutputFormat = "table",
) -> int:
    """Print and optionally persist public timeline items."""
    if log_jsonl is not None:
        log_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with log_jsonl.open("a", encoding="utf-8") as file:
            for item in items:
                file.write(item.model_dump_json() + "\n")

    if show_items:
        print_timeline(items, output_format=output_format)
    return next_after


def print_timeline(items: list[GameTimelineItem], *, output_format: OutputFormat = "table") -> None:
    """Print public timeline items."""
    if output_format != "table":
        print_json(items, output_format=output_format)
        return

    for item in items:
        console.print(f"[dim]{item.sequence}[/dim] [bold]{item.event_type}[/bold] {item.payload}")


def print_game_summaries(
    games: list[PublicGameSummary],
    *,
    output_format: OutputFormat = "table",
) -> None:
    """Print public game summaries."""
    if output_format != "table":
        print_json(games, output_format=output_format)
        return

    table = Table(title="Games")
    table.add_column("Game", overflow="fold")
    table.add_column("Status", no_wrap=True)
    table.add_column("Phase", no_wrap=True)
    table.add_column("Day", justify="right")
    table.add_column("Winner", no_wrap=True)
    table.add_column("Turns", justify="right")
    for game in games:
        table.add_row(
            game.game_id,
            game.status,
            game.phase,
            str(game.day),
            game.winner or "-",
            str(game.turn_count),
        )
    console.print(table)


def print_timeline_table(
    items: list[GameTimelineItem],
    *,
    output_format: OutputFormat = "table",
) -> None:
    """Print public timeline records in a table."""
    if output_format != "table":
        print_json(items, output_format=output_format)
        return

    table = Table(title="Game Timeline")
    table.add_column("Seq", justify="right", no_wrap=True)
    table.add_column("Event", no_wrap=True)
    table.add_column("Phase", no_wrap=True)
    table.add_column("Actor", overflow="fold")
    table.add_column("Payload", overflow="fold")
    for item in items:
        table.add_row(
            str(item.sequence),
            item.event_type,
            item.phase or "-",
            item.actor_id or "-",
            str(item.payload),
        )
    console.print(table)


def print_json(value: Any, *, output_format: OutputFormat) -> None:
    """Print JSON or JSONL for script-friendly command output."""
    if output_format == "jsonl":
        values = value if isinstance(value, list) else [value]
        for item in values:
            print(_json_line(item))
        return
    print(json.dumps(_json_value(value), ensure_ascii=False, indent=2, default=str))


def _json_line(value: Any) -> str:
    return json.dumps(_json_value(value), ensure_ascii=False, default=str, separators=(",", ":"))


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value
