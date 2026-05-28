"""Rich output helpers for the command line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from werewolf_agent.contracts.schemas import (
    PrivateObservationResponse,
    PublicGameEvent,
    PublicGameRunSummary,
    PublicGameState,
    PublicGameTurn,
    RulesetResponse,
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


def print_ruleset(ruleset: RulesetResponse, *, output_format: OutputFormat = "table") -> None:
    """Print public ruleset metadata."""
    if output_format != "table":
        print_json(ruleset, output_format=output_format)
        return

    table = Table(title=f"Ruleset {ruleset.id}")
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", overflow="fold")
    table.add_row("name", ruleset.name)
    table.add_row("description", ruleset.description)
    table.add_row("player count", str(ruleset.player_count))
    table.add_row("roles", ", ".join(item["id"] for item in ruleset.roles))
    table.add_row("phases", ", ".join(item["id"] for item in ruleset.phases))
    table.add_row("agent types", ", ".join(item["id"] for item in ruleset.agent_types))
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
    response: PrivateObservationResponse,
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


def consume_events(
    events: list[PublicGameEvent],
    *,
    next_after: int,
    log_jsonl: Path | None,
    show_events: bool,
    output_format: OutputFormat = "table",
) -> int:
    """Print and optionally persist public events."""
    if log_jsonl is not None:
        log_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with log_jsonl.open("a", encoding="utf-8") as file:
            for event in events:
                file.write(event.model_dump_json() + "\n")

    if show_events:
        print_events(events, output_format=output_format)
    return next_after


def print_events(events: list[PublicGameEvent], *, output_format: OutputFormat = "table") -> None:
    """Print public events."""
    if output_format != "table":
        print_json(events, output_format=output_format)
        return

    for event in events:
        console.print(
            f"[dim]{event.sequence}[/dim] [bold]{event.event_type}[/bold] {event.payload}"
        )


def print_run_summaries(
    runs: list[PublicGameRunSummary],
    *,
    output_format: OutputFormat = "table",
) -> None:
    """Print public run summaries."""
    if output_format != "table":
        print_json(runs, output_format=output_format)
        return

    table = Table(title="Game Runs")
    table.add_column("Game", overflow="fold")
    table.add_column("Status", no_wrap=True)
    table.add_column("Phase", no_wrap=True)
    table.add_column("Day", justify="right")
    table.add_column("Winner", no_wrap=True)
    table.add_column("Turns", justify="right")
    for run in runs:
        table.add_row(
            run.game_id,
            run.status,
            run.phase,
            str(run.day),
            run.winner or "-",
            str(run.turn_count),
        )
    console.print(table)


def print_turns(turns: list[PublicGameTurn], *, output_format: OutputFormat = "table") -> None:
    """Print public turn timeline records."""
    if output_format != "table":
        print_json(turns, output_format=output_format)
        return

    table = Table(title="Game Turns")
    table.add_column("Seq", justify="right", no_wrap=True)
    table.add_column("Event", no_wrap=True)
    table.add_column("Phase", no_wrap=True)
    table.add_column("Actor", overflow="fold")
    table.add_column("Payload", overflow="fold")
    for turn in turns:
        table.add_row(
            str(turn.sequence),
            turn.event_type,
            turn.phase or "-",
            turn.actor_id or "-",
            str(turn.payload),
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
