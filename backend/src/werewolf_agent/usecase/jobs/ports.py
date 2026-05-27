"""Ports implemented by outer layers for game use cases."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from werewolf_agent.domain.models import Action, Observation
from werewolf_agent.usecase.jobs.models import (
    EventToPersist,
    GameRunUpdate,
    NewGameRun,
    StoredGameEvent,
    StoredGameRun,
)


class AgentRuntime(Protocol):
    """Runtime agent capable of selecting one action from an observation."""

    def act(self, observation: Observation) -> Action:
        """Return one structured action for the given observation."""


class AgentFactory(Protocol):
    """Factory for phase-driving agents."""

    def create(self, player_id: str, *, seed: int) -> AgentRuntime:
        """Create an agent instance for one player and deterministic seed."""


class RandomFactory(Protocol):
    """Factory for deterministic random generators."""

    def __call__(self, seed: int | None = None) -> random.Random:
        """Return a random generator for the given seed."""


class Logger(Protocol):
    """Small logging port used by use cases."""

    def debug(self, msg: object, *args: object, **kwargs: object) -> None:
        """Log a debug message."""


class GameRunRepository(Protocol):
    """Persistence operations required by game use cases."""

    def create(self, run: NewGameRun) -> StoredGameRun:
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
        events: Sequence[EventToPersist],
    ) -> list[StoredGameEvent]:
        """Append events and assign stream sequence numbers."""

    def list_public_events(self, run_id: UUID, *, after: int) -> list[StoredGameEvent]:
        """Return public events after the sequence cursor."""
