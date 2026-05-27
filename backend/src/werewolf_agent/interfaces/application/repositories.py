"""Django persistence adapters for game use cases."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from django.db.models import Max

from werewolf_agent.interfaces.api.games.models import GameEventRecord, GameRun
from werewolf_agent.usecase.jobs import (
    EventToPersist,
    GameRunUpdate,
    NewGameRun,
    StoredGameEvent,
    StoredGameRun,
)


class DjangoGameRunRepository:
    """Django-backed implementation of the game run repository port."""

    def create(self, run: NewGameRun) -> StoredGameRun:
        """Persist a new game run."""
        model = GameRun.objects.create(
            id=run.id,
            status=run.status,
            phase=run.phase,
            day=run.day,
            seed=run.seed,
            config=run.config,
            public_state=run.public_state,
            private_state=run.private_state,
            version=run.version,
        )
        return _stored_run(model)

    def get(self, game_id: UUID) -> StoredGameRun | None:
        """Return a game run if it exists."""
        try:
            return _stored_run(GameRun.objects.get(id=game_id))
        except GameRun.DoesNotExist:
            return None

    def get_for_update(self, game_id: UUID) -> StoredGameRun | None:
        """Return a game run locked for update if it exists."""
        try:
            return _stored_run(GameRun.objects.select_for_update().get(id=game_id))
        except GameRun.DoesNotExist:
            return None

    def save(self, update: GameRunUpdate) -> StoredGameRun:
        """Persist mutable fields for one game run."""
        model = GameRun.objects.get(id=update.id)
        model.status = update.status
        model.phase = update.phase
        model.day = update.day
        model.public_state = update.public_state
        model.private_state = update.private_state
        model.version = update.version
        model.save(
            update_fields=[
                "status",
                "phase",
                "day",
                "public_state",
                "private_state",
                "version",
                "updated_at",
            ]
        )
        return _stored_run(model)

    def append_events(
        self,
        run_id: UUID,
        events: Sequence[EventToPersist],
    ) -> list[StoredGameEvent]:
        """Append events and assign stream sequence numbers."""
        if not events:
            return []

        last_sequence = (
            GameEventRecord.objects.filter(run_id=run_id).aggregate(max_sequence=Max("sequence"))[
                "max_sequence"
            ]
            or 0
        )
        records = []
        for offset, event in enumerate(events, start=1):
            records.append(
                GameEventRecord.objects.create(
                    run_id=run_id,
                    sequence=last_sequence + offset,
                    visibility=event.visibility,
                    phase=event.phase,
                    day=event.day,
                    actor_id=event.actor_id,
                    event_type=event.event_type,
                    payload=event.payload,
                )
            )
        return [_stored_event(record) for record in records]

    def list_public_events(self, run_id: UUID, *, after: int) -> list[StoredGameEvent]:
        """Return public events after the sequence cursor."""
        records = GameEventRecord.objects.filter(
            run_id=run_id,
            visibility=GameEventRecord.VISIBILITY_PUBLIC,
            sequence__gt=after,
        ).order_by("sequence")
        return [_stored_event(record) for record in records]


def _stored_run(model: GameRun) -> StoredGameRun:
    return StoredGameRun(
        id=model.id,
        status=model.status,
        phase=model.phase,
        day=model.day,
        seed=model.seed,
        config=_json_object(model.config),
        public_state=_json_object(model.public_state),
        private_state=_json_object(model.private_state),
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _stored_event(model: GameEventRecord) -> StoredGameEvent:
    return StoredGameEvent(
        sequence=model.sequence,
        event_id=model.event_id,
        visibility=model.visibility,
        phase=model.phase,
        day=model.day,
        actor_id=model.actor_id,
        event_type=model.event_type,
        payload=_json_object(model.payload),
        occurred_at=model.occurred_at,
    )


def _json_object(payload: Any) -> dict[str, Any]:
    return dict(payload or {})
