"""SQLAlchemy persistence adapters for game use cases."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from werewolf_agent.commons.shared.messages import message_game_run_not_found
from werewolf_agent.interface.application.models import (
    GameEventModel,
    GameRunModel,
    GameRunSummaryModel,
    GameTurnModel,
    max_event_sequence,
    max_turn_sequence,
    utc_now,
)
from werewolf_agent.usecase.jobs import (
    GameEventCreate,
    GameRepository,
    GameRunCreate,
    GameRunUpdate,
    GameStatus,
    StoredGameEvent,
    StoredGameRun,
    StoredGameRunSummary,
    StoredGameTurn,
)


class SqlAlchemyGameRunRepository(GameRepository):
    """SQLAlchemy-backed implementation of the game run repository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, run: GameRunCreate) -> StoredGameRun:
        """Persist a new game run."""
        now = utc_now()
        model = GameRunModel(
            id=str(run.id),
            status=run.status,
            phase=run.phase,
            day=run.day,
            seed=run.seed,
            config=run.config,
            public_state=run.public_state,
            private_state=run.private_state,
            version=run.version,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        self._session.flush()
        self._upsert_summary(model)
        return _stored_run(model)

    def get(self, game_id: UUID) -> StoredGameRun | None:
        """Return a game run if it exists."""
        model = self._session.get(GameRunModel, str(game_id))
        if model is None:
            return None
        return _stored_run(model)

    def list_run_summaries(
        self,
        *,
        status: GameStatus | None,
        limit: int,
        offset: int,
    ) -> list[StoredGameRunSummary]:
        """Return a page of persisted game run summaries."""
        statement = select(GameRunSummaryModel).order_by(GameRunSummaryModel.created_at.desc())
        if status is not None:
            statement = statement.where(GameRunSummaryModel.status == status)
        statement = statement.offset(offset).limit(limit)
        return [_stored_summary(record) for record in self._session.scalars(statement)]

    def get_for_update(self, game_id: UUID) -> StoredGameRun | None:
        """Return a game run locked for update if it exists."""
        statement = select(GameRunModel).where(GameRunModel.id == str(game_id)).with_for_update()
        model = self._session.scalars(statement).one_or_none()
        if model is None:
            return None
        return _stored_run(model)

    def save(self, update: GameRunUpdate) -> StoredGameRun:
        """Persist mutable fields for one game run."""
        model = self._session.get(GameRunModel, str(update.id))
        if model is None:
            raise KeyError(message_game_run_not_found(update.id))
        model.status = update.status
        model.phase = update.phase
        model.day = update.day
        model.public_state = update.public_state
        model.private_state = update.private_state
        model.version = update.version
        model.updated_at = utc_now()
        self._session.flush()
        self._upsert_summary(model)
        return _stored_run(model)

    def append_events(
        self,
        run_id: UUID,
        events: Sequence[GameEventCreate],
    ) -> list[StoredGameEvent]:
        """Append events and assign stream sequence numbers."""
        if not events:
            return []

        last_sequence = (
            self._session.scalar(
                select(max_event_sequence()).where(GameEventModel.run_id == str(run_id))
            )
            or 0
        )
        records = []
        for offset, event in enumerate(events, start=1):
            records.append(
                GameEventModel(
                    run_id=str(run_id),
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
        self._append_turns_for_events(run_id, records)
        run = self._session.get(GameRunModel, str(run_id))
        if run is not None:
            self._upsert_summary(run)
        return [_stored_event(record) for record in records]

    def list_public_events(
        self,
        run_id: UUID,
        *,
        after: int,
        limit: int,
    ) -> list[StoredGameEvent]:
        """Return public events after the sequence cursor."""
        statement = (
            select(GameEventModel)
            .where(
                GameEventModel.run_id == str(run_id),
                GameEventModel.visibility == "public",
                GameEventModel.sequence > after,
            )
            .order_by(GameEventModel.sequence)
            .limit(limit)
        )
        return [_stored_event(record) for record in self._session.scalars(statement)]

    def list_public_turns(
        self,
        run_id: UUID,
        *,
        after: int,
        limit: int,
    ) -> list[StoredGameTurn]:
        """Return public turn records after the sequence cursor."""
        statement = (
            select(GameTurnModel)
            .where(
                GameTurnModel.run_id == str(run_id),
                GameTurnModel.sequence > after,
            )
            .order_by(GameTurnModel.sequence)
            .limit(limit)
        )
        return [_stored_turn(record) for record in self._session.scalars(statement)]

    def _append_turns_for_events(
        self,
        run_id: UUID,
        events: Sequence[GameEventModel],
    ) -> None:
        public_events = [event for event in events if event.visibility == "public"]
        if not public_events:
            return

        run = self._session.get(GameRunModel, str(run_id))
        if run is None:
            return

        last_sequence = (
            self._session.scalar(
                select(max_turn_sequence()).where(GameTurnModel.run_id == str(run_id))
            )
            or 0
        )
        turns = [
            GameTurnModel(
                run_id=str(run_id),
                sequence=last_sequence + offset,
                event_sequence=event.sequence,
                version=run.version,
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

    def _upsert_summary(self, run: GameRunModel) -> None:
        state = _json_object(run.public_state)
        summary_payload = _json_object(state.get("summary"))
        turn_count = int(
            self._session.scalar(select(max_turn_sequence()).where(GameTurnModel.run_id == run.id))
            or 0
        )
        summary = self._session.get(GameRunSummaryModel, run.id)
        if summary is None:
            summary = GameRunSummaryModel(run_id=run.id)
            self._session.add(summary)

        summary.status = run.status
        summary.phase = run.phase
        summary.day = run.day
        summary.version = run.version
        summary.seed = run.seed
        summary.player_count = len(state.get("players") or [])
        summary.alive_count = int(summary_payload.get("alive_count") or 0)
        summary.winner = state.get("winner")
        summary.step_count = max(run.version - 1, 0)
        summary.turn_count = turn_count
        summary.created_at = run.created_at
        summary.updated_at = run.updated_at
        summary.completed_at = run.updated_at if run.status == "completed" else None
        self._session.flush()


def _stored_run(model: GameRunModel) -> StoredGameRun:
    return StoredGameRun.model_validate(
        {
            "id": UUID(model.id),
            "status": model.status,
            "phase": model.phase,
            "day": model.day,
            "seed": model.seed,
            "config": _json_object(model.config),
            "public_state": _json_object(model.public_state),
            "private_state": _json_object(model.private_state),
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


def _stored_summary(model: GameRunSummaryModel) -> StoredGameRunSummary:
    return StoredGameRunSummary.model_validate(
        {
            "game_id": UUID(model.run_id),
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


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
