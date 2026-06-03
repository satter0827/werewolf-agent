"""Internal projections from full domain state to public result payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from werewolf_agent.commons.shared.constants import DEFAULT_NARRATION_MODE, NARRATION_MODE_NONE
from werewolf_agent.commons.shared.definitions import NarrationProfileDefinition
from werewolf_agent.commons.shared.validation import public_generated_player_label
from werewolf_agent.contracts import (
    GAME_STATUS_COMPLETED,
    GAME_STATUS_RUNNING,
    GamePhase,
    GameStatus,
    Winner,
)
from werewolf_agent.domain.game.models import (
    FACTION_VILLAGE,
    FACTION_WEREWOLF,
    DomainEvent,
    GameSnapshot,
    Phase,
    PlayerStatus,
)
from werewolf_agent.usecase.jobs.games import (
    GameEventCreate,
    GameTimelineItem,
    PublicGameState,
    PublicGameSummary,
    PublicPlayerState,
    StoredGame,
    StoredGameSummary,
    StoredGameTurn,
)

PUBLIC_EVENT_PAYLOAD_KEYS: dict[str, frozenset[str]] = {
    "game_started": frozenset({"player_count"}),
    "phase_started": frozenset({"phase"}),
    "speech_recorded": frozenset({"message"}),
    "vote_submitted": frozenset({"target_id"}),
    "vote_resolved": frozenset({"eliminated_player_id", "counts", "tied_player_ids"}),
    "night_resolved": frozenset({"killed_player_id"}),
    "game_finished": frozenset({"winner", "reason"}),
}


def public_state_payload_from_game(game: StoredGame) -> dict[str, Any]:
    """Return public game state payload with persistence timestamps attached."""
    payload = dict(game.public_state)
    payload["created_at"] = game.created_at
    payload["updated_at"] = game.updated_at
    return PublicGameState.model_validate(payload).model_dump(mode="json")


def public_state_payload_from_snapshot(
    snapshot: GameSnapshot,
    *,
    game_id: str,
    version: int,
    seed: int | None,
    created_at: datetime | None = None,
    scenario_id: str | None = None,
    scenario_name: str | None = None,
    narration_mode: str = DEFAULT_NARRATION_MODE,
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
        game_id=game_id,
        status=status_from_snapshot(snapshot),
        phase=cast(GamePhase, snapshot.phase.value),
        day=snapshot.day,
        version=version,
        seed=seed,
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        narration_mode=cast(Any, narration_mode),
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


def public_game_summary_payload_from_record(record: StoredGameSummary) -> dict[str, Any]:
    """Project a stored game summary into a public payload."""
    summary = PublicGameSummary(
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
    payload = dict(record.payload)
    narration = payload.pop("narration", None)
    turn = GameTimelineItem(
        sequence=record.sequence,
        event_sequence=record.event_sequence,
        version=record.version,
        phase=record.phase,
        day=record.day,
        actor_id=record.actor_id,
        event_type=record.event_type,
        narration=str(narration) if narration is not None else None,
        payload=payload,
        occurred_at=record.occurred_at,
    )
    return turn.model_dump(mode="json")


def events_to_create(
    events: list[DomainEvent],
    *,
    narration_profile: NarrationProfileDefinition | None = None,
    narration_mode: str = DEFAULT_NARRATION_MODE,
) -> list[GameEventCreate]:
    """Return sanitized event data ready for an outer persistence adapter."""
    return [
        event_to_create(
            event,
            narration_profile=narration_profile,
            narration_mode=narration_mode,
        )
        for event in events
    ]


def event_to_create(
    event: DomainEvent,
    *,
    narration_profile: NarrationProfileDefinition | None = None,
    narration_mode: str = DEFAULT_NARRATION_MODE,
) -> GameEventCreate:
    """Return sanitized persistable event data for one domain event."""
    payload = public_safe_payload(event)
    narration = public_narration(event, payload, narration_profile, narration_mode=narration_mode)
    if narration:
        payload["narration"] = narration
    return GameEventCreate(
        visibility=event.visibility.value,
        phase=cast(GamePhase, event.phase.value) if event.phase is not None else None,
        day=event.day,
        actor_id=event.actor_id,
        event_type=event.event_type,
        payload=payload,
    )


def public_safe_payload(event: DomainEvent) -> dict[str, Any]:
    """Remove fields that must never appear in public event payloads."""
    allowed_keys = PUBLIC_EVENT_PAYLOAD_KEYS.get(event.event_type)
    payload = (
        {key: event.payload[key] for key in allowed_keys if key in event.payload}
        if allowed_keys is not None
        else {}
    )
    if event.event_type == "game_finished":
        winner = payload.get("winner")
        if winner == FACTION_VILLAGE:
            payload["winner"] = "villagers"
        elif winner == FACTION_WEREWOLF:
            payload["winner"] = "werewolves"
    return payload


def public_narration(
    event: DomainEvent,
    payload: dict[str, Any],
    narration_profile: NarrationProfileDefinition | None,
    *,
    narration_mode: str,
) -> str:
    """Return one public-safe narration line for a public event."""
    if narration_mode == NARRATION_MODE_NONE or narration_profile is None:
        return ""
    event_definition = narration_profile.events.get(event.event_type)
    if event_definition is None:
        return ""
    template = event_definition.templates[0]
    values = {
        "day": event.day if event.day is not None else "",
        "phase": event.phase.value if event.phase is not None else "",
        "phase_label": _phase_label(event.phase.value if event.phase is not None else ""),
        "actor": _public_player_label(event.actor_id),
        "player_count": payload.get("player_count", ""),
        "eliminated_player": _public_player_label(payload.get("eliminated_player_id")),
        "killed_player": _public_player_label(payload.get("killed_player_id")),
        "winner": payload.get("winner", ""),
        "winner_label": _winner_label(payload.get("winner")),
    }
    try:
        return template.format(**values)
    except (KeyError, ValueError):
        return ""


def _public_player_label(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    return public_generated_player_label(text) or text


def _phase_label(value: str) -> str:
    return {
        "night": "夜",
        "day_discussion": "話し合い",
        "voting": "投票",
        "finished": "終了",
    }.get(value, value)


def _winner_label(value: object) -> str:
    return {
        "villagers": "村人陣営",
        "werewolves": "人狼陣営",
    }.get(str(value), str(value) if value is not None else "")


def status_from_snapshot(snapshot: GameSnapshot) -> GameStatus:
    """Return the public game status for a domain snapshot."""
    if snapshot.phase is Phase.FINISHED:
        return GAME_STATUS_COMPLETED
    return GAME_STATUS_RUNNING


def winner_from_snapshot(snapshot: GameSnapshot) -> Winner | None:
    """Return the public winner value for a domain snapshot."""
    if snapshot.win_result is None:
        return None
    if snapshot.win_result.winner == FACTION_VILLAGE:
        return "villagers"
    return "werewolves"
