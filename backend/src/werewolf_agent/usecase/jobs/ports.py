"""Ports implemented by outer layers for game jobs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from werewolf_agent.usecase.jobs.models import (
    GameEventCreate,
    GameRunCreate,
    GameRunUpdate,
    StoredGameEvent,
    StoredGameRun,
)


class GameRepository(Protocol):
    """Persistence operations required by stateless game jobs."""

    def create(self, run: GameRunCreate) -> StoredGameRun:
        """Persist a new game run."""

    def get(self, game_id: UUID) -> StoredGameRun | None:
        """Return a game run if it exists."""

    def get_for_update(self, game_id: UUID) -> StoredGameRun | None:
        """Return a game run locked for update if it exists."""

    def save(self, update: GameRunUpdate) -> StoredGameRun:
        """Persist mutable fields for one game run."""

    def append_events(
        self,
        run_id: UUID,
        events: Sequence[GameEventCreate],
    ) -> list[StoredGameEvent]:
        """Append events and assign stream sequence numbers."""

    def list_public_events(self, run_id: UUID, *, after: int) -> list[StoredGameEvent]:
        """Return public events after the sequence cursor."""
