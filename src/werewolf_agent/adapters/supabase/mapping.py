"""Map Supabase rows into application persistence records."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from werewolf_agent.application.models import (
    StoredGame,
    StoredGameEvent,
    StoredGameSummary,
    StoredGameTurn,
)


def stored_game(row: Mapping[str, Any]) -> StoredGame:
    """Map a joined game and snapshot row."""
    return StoredGame.model_validate(
        {
            "id": row["game_id"],
            "status": row["status"],
            "phase": row["phase"],
            "day": row["day"],
            "seed": row.get("seed"),
            "config": _object(row.get("config")),
            "public_state": _object(row.get("public_state")),
            "private_state": _object(row.get("private_state")),
            "pending_actions": _object(row.get("pending_actions")),
            "version": row["version"],
            "created_at": _aware(row["created_at"]),
            "updated_at": _aware(row["updated_at"]),
        }
    )


def stored_event(row: Mapping[str, Any]) -> StoredGameEvent:
    """Map a game event row."""
    return StoredGameEvent.model_validate(
        {
            "sequence": row["sequence"],
            "event_id": row["event_id"],
            "visibility": row["visibility"],
            "phase": row.get("phase"),
            "day": row.get("day"),
            "actor_id": row.get("actor_id"),
            "event_type": row["event_type"],
            "payload": _object(row.get("payload")),
            "occurred_at": _aware(row["occurred_at"]),
        }
    )


def stored_summary(row: Mapping[str, Any]) -> StoredGameSummary:
    """Map a public game summary row."""
    return StoredGameSummary.model_validate(
        {
            "game_id": row["game_id"],
            "status": row["status"],
            "phase": row["phase"],
            "day": row["day"],
            "version": row["version"],
            "seed": row.get("seed"),
            "player_count": row["player_count"],
            "alive_count": row["alive_count"],
            "winner": row.get("winner"),
            "step_count": row["step_count"],
            "turn_count": row["turn_count"],
            "created_at": _aware(row["created_at"]),
            "updated_at": _aware(row["updated_at"]),
            "completed_at": _aware(row["completed_at"]) if row.get("completed_at") else None,
        }
    )


def stored_turn(row: Mapping[str, Any]) -> StoredGameTurn:
    """Map a public turn row."""
    return StoredGameTurn.model_validate(
        {
            "sequence": row["sequence"],
            "event_sequence": row["event_sequence"],
            "version": row["version"],
            "phase": row.get("phase"),
            "day": row.get("day"),
            "actor_id": row.get("actor_id"),
            "event_type": row["event_type"],
            "payload": _object(row.get("payload")),
            "occurred_at": _aware(row["occurred_at"]),
        }
    )


def _object(payload: Any) -> dict[str, Any]:
    return dict(payload) if isinstance(payload, Mapping) else {}


def _aware(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


__all__ = ["stored_event", "stored_game", "stored_summary", "stored_turn"]
