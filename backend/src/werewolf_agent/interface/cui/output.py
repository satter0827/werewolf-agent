"""Rich output helpers for the command line interface."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from werewolf_agent.interface.shared.schemas import PublicGameEvent, PublicGameState

console = Console()


def print_state(state: PublicGameState) -> None:
    """Print a compact public game state table."""
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


def consume_events(
    events: list[PublicGameEvent],
    *,
    next_after: int,
    log_jsonl: Path | None,
    show_events: bool,
) -> int:
    """Print and optionally persist public events."""
    if log_jsonl is not None:
        log_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with log_jsonl.open("a", encoding="utf-8") as file:
            for event in events:
                file.write(event.model_dump_json() + "\n")

    if show_events:
        for event in events:
            console.print(
                f"[dim]{event.sequence}[/dim] [bold]{event.event_type}[/bold] {event.payload}"
            )
    return next_after
