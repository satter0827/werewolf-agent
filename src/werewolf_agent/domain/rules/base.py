"""Stateless extension points for game-rule algorithms."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from werewolf_agent.domain.errors import RuleViolation
from werewolf_agent.domain.state import (
    Action,
    GameEvent,
    GameState,
    GameView,
    PendingActions,
    WinResult,
)


@dataclass(frozen=True)
class RuleContext:
    """Immutable input shared by rule policies."""

    state: GameState
    pending: PendingActions


class ActionPolicy(ABC):
    """Validate one submitted action without retaining runtime state."""

    @abstractmethod
    def validate(self, action: Action, context: RuleContext) -> Sequence[RuleViolation]:
        """Return every violation found for an action."""


class ResolutionPolicy(ABC):
    """Resolve one accepted action without retaining runtime state."""

    @abstractmethod
    def resolve(
        self,
        action: Action,
        context: RuleContext,
    ) -> tuple[GameState, PendingActions, list[GameEvent]]:
        """Return the atomic result of one action."""


class PhasePolicy(ABC):
    """Check and resolve one phase transition."""

    @abstractmethod
    def violations(self, context: RuleContext) -> Sequence[RuleViolation]:
        """Return violations that currently prevent phase advancement."""

    @abstractmethod
    def advance(
        self,
        context: RuleContext,
        random_source: random.Random,
    ) -> tuple[GameState, PendingActions, list[GameEvent]]:
        """Return the atomic result of advancing one phase."""


class VictoryPolicy(ABC):
    """Evaluate a winner from one immutable state."""

    @abstractmethod
    def evaluate(self, context: RuleContext) -> WinResult | None:
        """Return a winner when the configured condition is satisfied."""


class VisibilityPolicy(ABC):
    """Build one player-specific view from private game state."""

    @abstractmethod
    def build_view(self, player_id: str, context: RuleContext) -> GameView:
        """Return only information visible to the requested player."""


__all__ = [
    "ActionPolicy",
    "PhasePolicy",
    "ResolutionPolicy",
    "RuleContext",
    "VictoryPolicy",
    "VisibilityPolicy",
]
