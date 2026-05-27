"""Ports implemented by outer layers for game jobs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from werewolf_agent.domain.game.models import Action, Observation
from werewolf_agent.usecase.jobs.models import (
    GameEventCreate,
    GameRunCreate,
    GameRunUpdate,
    GameStatus,
    StoredGameEvent,
    StoredGameRun,
    StoredGameRunSummary,
    StoredGameTurn,
)


class PlayerAgent(Protocol):
    """Automated actor used by game jobs without coupling to provider details."""

    def act(self, observation: Observation) -> Action:
        """Return one structured action for the given visible observation."""


class AgentFactory(Protocol):
    """Factory for deterministic player agents."""

    def create(self, player_id: str, *, seed: int) -> PlayerAgent:
        """Create one player agent for a deterministic run step."""


class GameRepository(Protocol):
    """Persistence operations required by stateless game jobs."""

    def create(self, run: GameRunCreate) -> StoredGameRun:
        """Persist a new game run."""

    def get(self, game_id: UUID) -> StoredGameRun | None:
        """Return a game run if it exists."""

    def get_for_update(self, game_id: UUID) -> StoredGameRun | None:
        """Return a game run locked for update if it exists."""

    def list_run_summaries(
        self,
        *,
        status: GameStatus | None,
        limit: int,
        offset: int,
    ) -> list[StoredGameRunSummary]:
        """Return a page of game run summaries."""

    def save(self, update: GameRunUpdate) -> StoredGameRun:
        """Persist mutable fields for one game run."""

    def append_events(
        self,
        run_id: UUID,
        events: Sequence[GameEventCreate],
    ) -> list[StoredGameEvent]:
        """Append events and assign stream sequence numbers."""

    def list_public_events(
        self,
        run_id: UUID,
        *,
        after: int,
        limit: int,
    ) -> list[StoredGameEvent]:
        """Return public events after the sequence cursor."""

    def list_public_turns(
        self,
        run_id: UUID,
        *,
        after: int,
        limit: int,
    ) -> list[StoredGameTurn]:
        """Return public turn records after the sequence cursor."""
