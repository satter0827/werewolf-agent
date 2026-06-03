"""SQLAlchemy persistence adapters for game use cases."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from werewolf_agent.commons.shared.messages import message_game_not_found
from werewolf_agent.interface.application.models import (
    GameEventModel,
    GameModel,
    GameSummaryModel,
    GameTurnModel,
    max_event_sequence,
    max_turn_sequence,
    utc_now,
)
from werewolf_agent.usecase.jobs import (
    GameEventCreate,
    GameRecordCreate,
    GameRecordUpdate,
    GameRepository,
    GameStatus,
    StoredGame,
    StoredGameEvent,
    StoredGameSummary,
    StoredGameTurn,
)


class SqlAlchemyGameRepository(GameRepository):
    """SQLAlchemy-backed implementation of the game repository port."""

    def __init__(self, session: Session) -> None:
        """Create a repository bound to one SQLAlchemy session."""
        self._session = session

    def create(self, game: GameRecordCreate) -> StoredGame:
        """Persist a new game."""
        now = utc_now()
        model = GameModel(
            id=str(game.id),
            status=game.status,
            phase=game.phase,
            day=game.day,
            seed=game.seed,
            config=game.config,
            public_state=game.public_state,
            private_state=game.private_state,
            pending_actions=game.pending_actions,
            manual_token_hashes=game.manual_token_hashes,
            version=game.version,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        self._session.flush()
        self._upsert_summary(model)
        return _stored_game(model)

    def get(self, game_id: UUID) -> StoredGame | None:
        """Return a game if it exists."""
        model = self._session.get(GameModel, str(game_id))
        if model is None:
            return None
        return _stored_game(model)

    def list_game_summaries(
        self,
        *,
        status: GameStatus | None,
        limit: int,
        offset: int,
    ) -> list[StoredGameSummary]:
        """Return a page of persisted game summaries."""
        statement = select(GameSummaryModel).order_by(GameSummaryModel.created_at.desc())
        if status is not None:
            statement = statement.where(GameSummaryModel.status == status)
        statement = statement.offset(offset).limit(limit)
        return [_stored_summary(record) for record in self._session.scalars(statement)]

    def get_for_update(self, game_id: UUID) -> StoredGame | None:
        """Return a game locked for update if it exists."""
        statement = select(GameModel).where(GameModel.id == str(game_id)).with_for_update()
        model = self._session.scalars(statement).one_or_none()
        if model is None:
            return None
        return _stored_game(model)

    def save(self, update: GameRecordUpdate) -> StoredGame:
        """Persist mutable fields for one game."""
        model = self._session.get(GameModel, str(update.id))
        if model is None:
            raise KeyError(message_game_not_found(update.id))
        model.status = update.status
        model.phase = update.phase
        model.day = update.day
        model.public_state = update.public_state
        model.private_state = update.private_state
        model.pending_actions = update.pending_actions
        model.version = update.version
        model.updated_at = utc_now()
        self._session.flush()
        self._upsert_summary(model)
        return _stored_game(model)

    def append_events(
        self,
        game_id: UUID,
        events: Sequence[GameEventCreate],
    ) -> list[StoredGameEvent]:
        """Append events and assign stream sequence numbers."""
        if not events:
            return []

        last_sequence = (
            self._session.scalar(
                select(max_event_sequence()).where(GameEventModel.game_id == str(game_id))
            )
            or 0
        )
        records = []
        for offset, event in enumerate(events, start=1):
            records.append(
                GameEventModel(
                    game_id=str(game_id),
                    sequence=last_sequence + offset,
                    visibility=event.visibility,
                    phase=event.phase,
                    day=event.day,
                    actor_id=event.actor_id,
                    event_type=event.event_type,
                    payload=event.payload,
                    occurred_at=utc_now(),
                )
            )
        self._session.add_all(records)
        self._session.flush()
        self._append_turns_for_events(game_id, records)
        game = self._session.get(GameModel, str(game_id))
        if game is not None:
            self._upsert_summary(game)
        return [_stored_event(record) for record in records]

    def latest_public_turn_sequence(self, game_id: UUID) -> int:
        """Return the latest public timeline sequence for one game."""
        return int(
            self._session.scalar(
                select(max_turn_sequence()).where(GameTurnModel.game_id == str(game_id))
            )
            or 0
        )

    def list_public_turns(
        self,
        game_id: UUID,
        *,
        after: int,
        limit: int,
    ) -> list[StoredGameTurn]:
        """Return public turn records after the sequence cursor."""
        statement = (
            select(GameTurnModel)
            .where(
                GameTurnModel.game_id == str(game_id),
                GameTurnModel.sequence > after,
            )
            .order_by(GameTurnModel.sequence)
            .limit(limit)
        )
        return [_stored_turn(record) for record in self._session.scalars(statement)]

    def _append_turns_for_events(
        self,
        game_id: UUID,
        events: Sequence[GameEventModel],
    ) -> None:
        public_events = [event for event in events if event.visibility == "public"]
        if not public_events:
            return

        game = self._session.get(GameModel, str(game_id))
        if game is None:
            return

        last_sequence = (
            self._session.scalar(
                select(max_turn_sequence()).where(GameTurnModel.game_id == str(game_id))
            )
            or 0
        )
        turns = [
            GameTurnModel(
                game_id=str(game_id),
                sequence=last_sequence + offset,
                event_sequence=event.sequence,
                version=game.version,
                phase=event.phase,
                day=event.day,
                actor_id=event.actor_id,
                event_type=event.event_type,
                payload=_json_object(event.payload),
                occurred_at=event.occurred_at,
            )
            for offset, event in enumerate(public_events, start=1)
        ]
        self._session.add_all(turns)
        self._session.flush()

    def _upsert_summary(self, game: GameModel) -> None:
        state = _json_object(game.public_state)
        summary_payload = _json_object(state.get("summary"))
        turn_count = int(
            self._session.scalar(
                select(max_turn_sequence()).where(GameTurnModel.game_id == game.id)
            )
            or 0
        )
        summary = self._session.get(GameSummaryModel, game.id)
        if summary is None:
            summary = GameSummaryModel(game_id=game.id)
            self._session.add(summary)

        summary.status = game.status
        summary.phase = game.phase
        summary.day = game.day
        summary.version = game.version
        summary.seed = game.seed
        summary.player_count = len(state.get("players") or [])
        summary.alive_count = int(summary_payload.get("alive_count") or 0)
        summary.winner = state.get("winner")
        summary.step_count = max(game.version - 1, 0)
        summary.turn_count = turn_count
        summary.created_at = game.created_at
        summary.updated_at = game.updated_at
        summary.completed_at = game.updated_at if game.status == "completed" else None
        self._session.flush()


def _stored_game(model: GameModel) -> StoredGame:
    return StoredGame.model_validate(
        {
            "id": UUID(model.id),
            "status": model.status,
            "phase": model.phase,
            "day": model.day,
            "seed": model.seed,
            "config": _json_object(model.config),
            "public_state": _json_object(model.public_state),
            "private_state": _json_object(model.private_state),
            "pending_actions": _json_object(model.pending_actions),
            "manual_token_hashes": _json_str_mapping(model.manual_token_hashes),
            "version": model.version,
            "created_at": _ensure_aware(model.created_at),
            "updated_at": _ensure_aware(model.updated_at),
        }
    )


def _stored_event(model: GameEventModel) -> StoredGameEvent:
    return StoredGameEvent.model_validate(
        {
            "sequence": model.sequence,
            "event_id": UUID(model.event_id),
            "visibility": model.visibility,
            "phase": model.phase,
            "day": model.day,
            "actor_id": model.actor_id,
            "event_type": model.event_type,
            "payload": _json_object(model.payload),
            "occurred_at": _ensure_aware(model.occurred_at),
        }
    )


def _stored_summary(model: GameSummaryModel) -> StoredGameSummary:
    return StoredGameSummary.model_validate(
        {
            "game_id": UUID(model.game_id),
            "status": model.status,
            "phase": model.phase,
            "day": model.day,
            "version": model.version,
            "seed": model.seed,
            "player_count": model.player_count,
            "alive_count": model.alive_count,
            "winner": model.winner,
            "step_count": model.step_count,
            "turn_count": model.turn_count,
            "created_at": _ensure_aware(model.created_at),
            "updated_at": _ensure_aware(model.updated_at),
            "completed_at": _ensure_aware(model.completed_at)
            if model.completed_at is not None
            else None,
        }
    )


def _stored_turn(model: GameTurnModel) -> StoredGameTurn:
    return StoredGameTurn.model_validate(
        {
            "sequence": model.sequence,
            "event_sequence": model.event_sequence,
            "version": model.version,
            "phase": model.phase,
            "day": model.day,
            "actor_id": model.actor_id,
            "event_type": model.event_type,
            "payload": _json_object(model.payload),
            "occurred_at": _ensure_aware(model.occurred_at),
        }
    )


def _json_object(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def _json_str_mapping(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
