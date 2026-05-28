"""Internal projections from full domain state to public result payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from werewolf_agent.domain.game.models import (
    DomainEvent,
    Faction,
    GameSnapshot,
    Phase,
    PlayerStatus,
)
from werewolf_agent.usecase.jobs.games import (
    GameEventCreate,
    GamePhase,
    GameStatus,
    PublicGameEvent,
    PublicGameRunSummary,
    PublicGameState,
    PublicGameTurn,
    PublicPlayerState,
    StoredGameEvent,
    StoredGameRun,
    StoredGameRunSummary,
    StoredGameTurn,
    Winner,
)


def public_state_payload_from_run(run: StoredGameRun) -> dict[str, Any]:
    """Return public game state payload with persistence timestamps attached."""
    payload = dict(run.public_state)
    payload["created_at"] = run.created_at
    payload["updated_at"] = run.updated_at
    return PublicGameState.model_validate(payload).model_dump(mode="json")


def public_state_payload_from_snapshot(
    snapshot: GameSnapshot,
    *,
    version: int,
    seed: int | None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Project a full domain snapshot into a public state payload."""
    players = [
        PublicPlayerState(
            id=player.id,
            name=player.name,
            alive=player.status is PlayerStatus.ALIVE,
            status=player.status.value,
            eliminated_day=player.eliminated_day,
            killed_night=player.killed_night,
        )
        for player in snapshot.players.values()
    ]
    alive_player_ids = [
        player.id for player in snapshot.players.values() if player.status is PlayerStatus.ALIVE
    ]
    eliminated_player_ids = [
        player.id for player in snapshot.players.values() if player.status is PlayerStatus.DEAD
    ]
    state = PublicGameState(
        game_id=snapshot.game_id,
        status=status_from_snapshot(snapshot),
        phase=cast(GamePhase, snapshot.phase.value),
        day=snapshot.day,
        version=version,
        seed=seed,
        players=players,
        alive_player_ids=alive_player_ids,
        eliminated_player_ids=eliminated_player_ids,
        winner=winner_from_snapshot(snapshot),
        summary={
            "alive_count": len(alive_player_ids),
            "eliminated_count": len(eliminated_player_ids),
            "speech_count": len(snapshot.history.speeches),
            "vote_rounds": len(snapshot.history.votes),
            "night_rounds": len(snapshot.history.nights),
        },
        created_at=created_at,
    )
    return state.model_dump(mode="json")


def public_event_payload_from_record(record: StoredGameEvent) -> dict[str, Any]:
    """Project a stored public event into a public event payload."""
    event = PublicGameEvent(
        sequence=record.sequence,
        event_id=record.event_id,
        event_type=record.event_type,
        phase=record.phase,
        day=record.day,
        actor_id=record.actor_id,
        visibility="public",
        payload=dict(record.payload),
        occurred_at=record.occurred_at,
    )
    return event.model_dump(mode="json")


def public_run_summary_payload_from_record(record: StoredGameRunSummary) -> dict[str, Any]:
    """Project a stored run summary into a public payload."""
    summary = PublicGameRunSummary(
        game_id=str(record.game_id),
        status=record.status,
        phase=record.phase,
        day=record.day,
        version=record.version,
        seed=record.seed,
        player_count=record.player_count,
        alive_count=record.alive_count,
        winner=record.winner,
        step_count=record.step_count,
        turn_count=record.turn_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
    )
    return summary.model_dump(mode="json")


def public_turn_payload_from_record(record: StoredGameTurn) -> dict[str, Any]:
    """Project a stored turn record into a public timeline payload."""
    turn = PublicGameTurn(
        sequence=record.sequence,
        event_sequence=record.event_sequence,
        version=record.version,
        phase=record.phase,
        day=record.day,
        actor_id=record.actor_id,
        event_type=record.event_type,
        payload=dict(record.payload),
        occurred_at=record.occurred_at,
    )
    return turn.model_dump(mode="json")


def events_to_create(events: list[DomainEvent]) -> list[GameEventCreate]:
    """Return sanitized event data ready for an outer persistence adapter."""
    return [event_to_create(event) for event in events]


def event_to_create(event: DomainEvent) -> GameEventCreate:
    """Return sanitized persistable event data for one domain event."""
    return GameEventCreate(
        visibility=event.visibility.value,
        phase=cast(GamePhase, event.phase.value) if event.phase is not None else None,
        day=event.day,
        actor_id=event.actor_id,
        event_type=event.event_type,
        payload=public_safe_payload(event),
    )


def public_safe_payload(event: DomainEvent) -> dict[str, Any]:
    """Remove fields that must never appear in public event payloads."""
    payload = dict(event.payload)
    if event.event_type == "game_started":
        payload.pop("role_counts", None)
    return payload


def status_from_snapshot(snapshot: GameSnapshot) -> GameStatus:
    """Return the public run status for a domain snapshot."""
    if snapshot.phase is Phase.FINISHED:
        return "completed"
    return "running"


def winner_from_snapshot(snapshot: GameSnapshot) -> Winner | None:
    """Return the public winner value for a domain snapshot."""
    if snapshot.win_result is None:
        return None
    if snapshot.win_result.winner is Faction.VILLAGE:
        return "villagers"
    return "werewolves"
