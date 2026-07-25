"""Persistence records owned by the application layer."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from werewolf_agent.application.models.base import ApplicationModel
from werewolf_agent.contracts import GamePhase, GameStatus, Winner

if TYPE_CHECKING:
    pass

EventVisibility = Literal["public", "player_private", "debug"]
ActionTypeId = str


class StoredGameTurn(ApplicationModel):
    """Turn read-model record loaded from an outer persistence adapter."""

    sequence: int
    event_sequence: int
    version: int
    phase: GamePhase | None = None
    day: int | None = None
    actor_id: str | None = None
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


class StoredGameSummary(ApplicationModel):
    """Game summary read model loaded from an outer persistence adapter."""

    game_id: UUID
    status: GameStatus
    phase: GamePhase
    day: int
    version: int
    seed: int | None
    player_count: int
    alive_count: int
    winner: Winner | None = None
    step_count: int
    turn_count: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRecordCreate(ApplicationModel):
    """New game data to be persisted by an outer repository."""

    id: UUID
    status: GameStatus
    phase: GamePhase
    day: int
    seed: int | None
    config: dict[str, Any]
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    pending_actions: dict[str, Any] = Field(default_factory=dict)
    version: int

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRecordUpdate(ApplicationModel):
    """Persistable updates for an existing game."""

    id: UUID
    status: GameStatus
    phase: GamePhase
    day: int
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    pending_actions: dict[str, Any] = Field(default_factory=dict)
    version: int

    model_config = ConfigDict(extra="forbid", frozen=True)


class StoredGame(ApplicationModel):
    """Game loaded from an outer persistence adapter."""

    id: UUID
    status: GameStatus
    phase: GamePhase
    day: int
    seed: int | None
    config: dict[str, Any]
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    pending_actions: dict[str, Any] = Field(default_factory=dict)
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


class StoredGameEvent(ApplicationModel):
    """Event record loaded from an outer persistence adapter."""

    sequence: int
    event_id: UUID
    visibility: EventVisibility
    phase: GamePhase | None = None
    day: int | None = None
    actor_id: str | None = None
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)
