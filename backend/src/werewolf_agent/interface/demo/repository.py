"""In-memory repository for unauthenticated demo play."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from uuid import UUID, uuid4

from werewolf_agent.commons.shared.messages import message_game_not_found
from werewolf_agent.contracts import GAME_STATUS_COMPLETED, GameStatus
from werewolf_agent.usecase.jobs import (
    GameEventCreate,
    GameRecordCreate,
    GameRecordUpdate,
    GameRepository,
    StoredGame,
    StoredGameEvent,
    StoredGameSummary,
    StoredGameTurn,
)


@dataclass
class _GameRow:
    game: StoredGame
    events: list[StoredGameEvent] = field(default_factory=list)
    turns: list[StoredGameTurn] = field(default_factory=list)


class InMemoryGameRepository(GameRepository):
    """Repository implementation scoped to one local process."""

    def __init__(self) -> None:
        """Create an empty repository."""
        self._rows: dict[UUID, _GameRow] = {}
        self._lock = RLock()

    def create(self, game: GameRecordCreate) -> StoredGame:
        """Persist a new game in memory."""
        now = _utc_now()
        stored = StoredGame.model_validate(
            {
                **game.model_dump(mode="python"),
                "created_at": now,
                "updated_at": now,
            }
        )
        with self._lock:
            self._rows[game.id] = _GameRow(game=_copy_game(stored))
        return _copy_game(stored)

    def get(self, game_id: UUID) -> StoredGame | None:
        """Return a game if it exists."""
        with self._lock:
            row = self._rows.get(game_id)
            return _copy_game(row.game) if row is not None else None

    def get_for_update(self, game_id: UUID) -> StoredGame | None:
        """Return a game for update.

        The process-wide lock protects every write, so no separate row lock is needed.
        """
        return self.get(game_id)

    def list_game_summaries(
        self,
        *,
        status: GameStatus | None,
        limit: int,
        offset: int,
    ) -> list[StoredGameSummary]:
        """Return demo game summaries."""
        with self._lock:
            summaries = [
                _summary(row.game, turn_count=len(row.turns))
                for row in self._rows.values()
                if status is None or row.game.status == status
            ]
        summaries.sort(key=lambda item: item.created_at, reverse=True)
        return summaries[offset : offset + limit]

    def save(self, update: GameRecordUpdate) -> StoredGame:
        """Persist mutable fields for one game."""
        with self._lock:
            row = self._rows.get(update.id)
            if row is None:
                raise KeyError(message_game_not_found(update.id))
            stored = row.game.model_copy(
                update={
                    "status": update.status,
                    "phase": update.phase,
                    "day": update.day,
                    "public_state": deepcopy(update.public_state),
                    "private_state": deepcopy(update.private_state),
                    "pending_actions": deepcopy(update.pending_actions),
                    "version": update.version,
                    "updated_at": _utc_now(),
                }
            )
            row.game = stored
            row.turns = [turn.model_copy(update={"version": update.version}) for turn in row.turns]
            return _copy_game(stored)

    def append_events(
        self,
        game_id: UUID,
        events: Sequence[GameEventCreate],
    ) -> list[StoredGameEvent]:
        """Append events and derive public turns."""
        if not events:
            return []
        with self._lock:
            row = self._rows.get(game_id)
            if row is None:
                raise KeyError(message_game_not_found(game_id))
            last_event_sequence = row.events[-1].sequence if row.events else 0
            last_turn_sequence = row.turns[-1].sequence if row.turns else 0
            stored_events: list[StoredGameEvent] = []
            for offset, event in enumerate(events, start=1):
                stored = StoredGameEvent(
                    sequence=last_event_sequence + offset,
                    event_id=uuid4(),
                    visibility=event.visibility,
                    phase=event.phase,
                    day=event.day,
                    actor_id=event.actor_id,
                    event_type=event.event_type,
                    payload=deepcopy(event.payload),
                    occurred_at=_utc_now(),
                )
                row.events.append(stored)
                stored_events.append(stored)
                if event.visibility == "public":
                    last_turn_sequence += 1
                    row.turns.append(
                        StoredGameTurn(
                            sequence=last_turn_sequence,
                            event_sequence=stored.sequence,
                            version=row.game.version,
                            phase=event.phase,
                            day=event.day,
                            actor_id=event.actor_id,
                            event_type=event.event_type,
                            payload=deepcopy(event.payload),
                            occurred_at=stored.occurred_at,
                        )
                    )
            return [event.model_copy(deep=True) for event in stored_events]

    def latest_public_turn_sequence(self, game_id: UUID) -> int:
        """Return the latest public timeline sequence."""
        with self._lock:
            row = self._rows.get(game_id)
            if row is None or not row.turns:
                return 0
            return row.turns[-1].sequence

    def list_public_turns(
        self,
        game_id: UUID,
        *,
        after: int,
        limit: int,
    ) -> list[StoredGameTurn]:
        """Return public turn records after a cursor."""
        with self._lock:
            row = self._rows.get(game_id)
            if row is None:
                return []
            return [turn.model_copy(deep=True) for turn in row.turns if turn.sequence > after][
                :limit
            ]


def _summary(game: StoredGame, *, turn_count: int) -> StoredGameSummary:
    public_state = dict(game.public_state)
    state_summary = public_state.get("summary")
    summary = state_summary if isinstance(state_summary, dict) else {}
    return StoredGameSummary(
        game_id=game.id,
        status=game.status,
        phase=game.phase,
        day=game.day,
        version=game.version,
        seed=game.seed,
        player_count=len(public_state.get("players") or []),
        alive_count=int(summary.get("alive_count") or 0),
        winner=public_state.get("winner"),
        step_count=max(game.version - 1, 0),
        turn_count=turn_count,
        created_at=game.created_at,
        updated_at=game.updated_at,
        completed_at=game.updated_at if game.status == GAME_STATUS_COMPLETED else None,
    )


def _copy_game(game: StoredGame) -> StoredGame:
    return game.model_copy(deep=True)


def _utc_now() -> datetime:
    return datetime.now(UTC)
