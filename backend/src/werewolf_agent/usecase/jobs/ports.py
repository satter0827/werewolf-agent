"""Ports implemented by outer layers for game jobs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from werewolf_agent.usecase.jobs.games import (
    GameEventCreate,
    GameRunCreate,
    GameRunUpdate,
    GameStatus,
    StoredGameEvent,
    StoredGameRun,
    StoredGameRunSummary,
    StoredGameTurn,
)


class GameRepository(Protocol):
    """Persistence operations required by stateless game jobs."""

    def create(self, run: GameRunCreate) -> StoredGameRun:
        """Persist a new game run.

        Args:
            run: Full persistence payload for the new run.

        Returns:
            Stored game run with repository-assigned timestamps.

        """

    def get(self, game_id: UUID) -> StoredGameRun | None:
        """Return a game run if it exists.

        Args:
            game_id: Game run id.

        Returns:
            Stored game run, or `None` when absent.

        """

    def get_for_update(self, game_id: UUID) -> StoredGameRun | None:
        """Return a game run locked for update if it exists.

        Args:
            game_id: Game run id.

        Returns:
            Stored game run, or `None` when absent.

        """

    def list_run_summaries(
        self,
        *,
        status: GameStatus | None,
        limit: int,
        offset: int,
    ) -> list[StoredGameRunSummary]:
        """Return a page of game run summaries.

        Args:
            status: Optional public run status filter.
            limit: Maximum number of summaries to return.
            offset: Result offset for pagination.

        Returns:
            Public run summaries in display order.

        """

    def save(self, update: GameRunUpdate) -> StoredGameRun:
        """Persist mutable fields for one game run.

        Args:
            update: Mutable run fields after a use case step.

        Returns:
            Updated stored game run.

        """

    def append_events(
        self,
        run_id: UUID,
        events: Sequence[GameEventCreate],
    ) -> list[StoredGameEvent]:
        """Append events and assign stream sequence numbers.

        Args:
            run_id: Game run id that owns the events.
            events: Domain-derived events to persist.

        Returns:
            Stored events with assigned sequence numbers.

        """

    def latest_public_turn_sequence(self, run_id: UUID) -> int:
        """Return the latest public timeline sequence for one game run.

        Args:
            run_id: Game run id that owns the timeline.

        Returns:
            Latest public timeline sequence, or `0` when the timeline is empty.

        """

    def list_public_turns(
        self,
        run_id: UUID,
        *,
        after: int,
        limit: int,
    ) -> list[StoredGameTurn]:
        """Return public turn records after the sequence cursor.

        Args:
            run_id: Game run id that owns the timeline.
            after: Exclusive turn sequence cursor.
            limit: Maximum number of turn records to return.

        Returns:
            Public turn records ordered by sequence.

        """
