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
    max_event_sequence,
    utc_now,
)
from werewolf_agent.usecase.jobs import (
    GameEventCreate,
    GameRepository,
    GameRunCreate,
    GameRunUpdate,
    StoredGameEvent,
    StoredGameRun,
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
        return _stored_run(model)

    def get(self, game_id: UUID) -> StoredGameRun | None:
        """Return a game run if it exists."""
        model = self._session.get(GameRunModel, str(game_id))
        if model is None:
            return None
        return _stored_run(model)

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
        return [_stored_event(record) for record in records]

    def list_public_events(self, run_id: UUID, *, after: int) -> list[StoredGameEvent]:
        """Return public events after the sequence cursor."""
        statement = (
            select(GameEventModel)
            .where(
                GameEventModel.run_id == str(run_id),
                GameEventModel.visibility == "public",
                GameEventModel.sequence > after,
            )
            .order_by(GameEventModel.sequence)
        )
        return [_stored_event(record) for record in self._session.scalars(statement)]


def _stored_run(model: GameRunModel) -> StoredGameRun:
    return StoredGameRun(
        id=UUID(model.id),
        status=model.status,
        phase=model.phase,
        day=model.day,
        seed=model.seed,
        config=_json_object(model.config),
        public_state=_json_object(model.public_state),
        private_state=_json_object(model.private_state),
        version=model.version,
        created_at=_ensure_aware(model.created_at),
        updated_at=_ensure_aware(model.updated_at),
    )


def _stored_event(model: GameEventModel) -> StoredGameEvent:
    return StoredGameEvent(
        sequence=model.sequence,
        event_id=UUID(model.event_id),
        visibility=model.visibility,
        phase=model.phase,
        day=model.day,
        actor_id=model.actor_id,
        event_type=model.event_type,
        payload=_json_object(model.payload),
        occurred_at=_ensure_aware(model.occurred_at),
    )


def _json_object(payload: Any) -> dict[str, Any]:
    return dict(payload or {})


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
