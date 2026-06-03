"""Ports implemented by outer layers for game jobs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from werewolf_agent.contracts import GameStatus
from werewolf_agent.usecase.jobs.games import (
    GameEventCreate,
    GameRecordCreate,
    GameRecordUpdate,
    StoredGame,
    StoredGameEvent,
    StoredGameSummary,
    StoredGameTurn,
)


class GameRepository(Protocol):
    """Persistence operations required by stateless game jobs."""

    def create(self, game: GameRecordCreate) -> StoredGame:
        """Persist a new game.

        Args:
            game: Full persistence payload for the new game.

        Returns:
            Stored game with repository-assigned timestamps.

        """

    def get(self, game_id: UUID) -> StoredGame | None:
        """Return a game if it exists.

        Args:
            game_id: Game id.

        Returns:
            Stored game, or `None` when absent.

        """

    def get_for_update(self, game_id: UUID) -> StoredGame | None:
        """Return a game locked for update if it exists.

        Args:
            game_id: Game id.

        Returns:
            Stored game, or `None` when absent.

        """

    def list_game_summaries(
        self,
        *,
        status: GameStatus | None,
        limit: int,
        offset: int,
    ) -> list[StoredGameSummary]:
        """Return a page of game summaries.

        Args:
            status: Optional public game status filter.
            limit: Maximum number of summaries to return.
            offset: Result offset for pagination.

        Returns:
            Public game summaries in display order.

        """

    def save(self, update: GameRecordUpdate) -> StoredGame:
        """Persist mutable fields for one game.

        Args:
            update: Mutable game fields after a use case step.

        Returns:
            Updated stored game.

        """

    def append_events(
        self,
        game_id: UUID,
        events: Sequence[GameEventCreate],
    ) -> list[StoredGameEvent]:
        """Append events and assign stream sequence numbers.

        Args:
            game_id: Game id that owns the events.
            events: Domain-derived events to persist.

        Returns:
            Stored events with assigned sequence numbers.

        """

    def latest_public_turn_sequence(self, game_id: UUID) -> int:
        """Return the latest public timeline sequence for one game.

        Args:
            game_id: Game id that owns the timeline.

        Returns:
            Latest public timeline sequence, or `0` when the timeline is empty.

        """

    def list_public_turns(
        self,
        game_id: UUID,
        *,
        after: int,
        limit: int,
    ) -> list[StoredGameTurn]:
        """Return public turn records after the sequence cursor.

        Args:
            game_id: Game id that owns the timeline.
            after: Exclusive turn sequence cursor.
            limit: Maximum number of turn records to return.

        Returns:
            Public turn records ordered by sequence.

        """
