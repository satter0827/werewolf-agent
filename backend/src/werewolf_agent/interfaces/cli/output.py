"""CLI output rendering and JSONL event writing."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from werewolf_agent.contracts.schemas import PublicGameEvent, PublicGameState

console = Console()


def consume_events(
    events: list[PublicGameEvent],
    *,
    next_after: int,
    log_jsonl: Path | None,
    show_events: bool,
) -> int:
    """Write and optionally render public events, then return the next cursor."""
    if log_jsonl is not None:
        append_events_jsonl(log_jsonl, events)
    if show_events:
        print_events(events)
    return next_after


def print_state(state: PublicGameState) -> None:
    """Render public game state as a terminal table."""
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


def print_events(events: list[PublicGameEvent]) -> None:
    """Render public game events as a terminal table."""
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
            event_detail(event),
        )
    console.print(table)


def event_detail(event: PublicGameEvent) -> str:
    """Return a compact terminal detail for one event."""
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


def append_events_jsonl(path: Path, events: list[PublicGameEvent]) -> None:
    """Append public events to a JSONL file."""
    if not events:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as output:
        for event in events:
            output.write(event.model_dump_json(exclude_none=True))
            output.write("\n")
