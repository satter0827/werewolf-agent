"""Supabase row mapping の application contract を検査する。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from werewolf_agent.adapters.supabase.mapping import (
    stored_event,
    stored_game,
    stored_summary,
    stored_turn,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_stored_game_maps_complete_repository_record() -> None:
    game_id = uuid4()
    result = stored_game(
        {
            "game_id": game_id,
            "status": "running",
            "phase": "night",
            "day": 1,
            "seed": 7,
            "config": {"mode": "fake"},
            "public_state": {"day": 1},
            "private_state": {"roles": {}},
            "pending_actions": {},
            "version": 2,
            "created_at": NOW,
            "updated_at": NOW,
        }
    )

    assert result.id == game_id
    assert result.status == "running"
    assert result.private_state == {"roles": {}}


def test_stored_event_maps_event_identity_and_visibility() -> None:
    event_id = uuid4()
    result = stored_event(
        {
            "sequence": 3,
            "event_id": event_id,
            "visibility": "public",
            "phase": "day_discussion",
            "day": 1,
            "actor_id": "player-1",
            "event_type": "speech",
            "payload": {"text": "hello"},
            "occurred_at": NOW,
        }
    )

    assert result.event_id == event_id
    assert result.actor_id == "player-1"


def test_stored_summary_maps_public_counts() -> None:
    game_id = uuid4()
    result = stored_summary(
        {
            "game_id": game_id,
            "status": "running",
            "phase": "night",
            "day": 1,
            "version": 2,
            "seed": 7,
            "player_count": 6,
            "alive_count": 5,
            "winner": None,
            "step_count": 3,
            "turn_count": 2,
            "created_at": NOW,
            "updated_at": NOW,
            "completed_at": None,
        }
    )

    assert result.game_id == game_id
    assert result.player_count == 6
    assert result.turn_count == 2


def test_stored_turn_maps_event_reference() -> None:
    result = stored_turn(
        {
            "sequence": 4,
            "event_sequence": 9,
            "version": 2,
            "phase": "day_discussion",
            "day": 1,
            "actor_id": None,
            "event_type": "phase_changed",
            "payload": {},
            "occurred_at": NOW,
        }
    )

    assert result.event_sequence == 9
    assert result.event_type == "phase_changed"
