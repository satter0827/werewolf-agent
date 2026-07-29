"""Persistence records owned by the application layer."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from werewolf_agent.application.models.base import ApplicationModel
from werewolf_agent.application.types import GamePhase, GameStatus, Winner

if TYPE_CHECKING:
    pass

EventVisibility = Literal["public", "player_private", "debug"]
ActionTypeId = str


class StoredGameTurn(ApplicationModel):
    """外側の永続化adapterから読み込んだturn記録を表す。"""

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
    """外側の永続化adapterから読み込んだゲーム概要を表す。"""

    game_id: UUID
    status: GameStatus
    phase: GamePhase
    day: int
    version: int
    seed: int | None
    scenario_id: str | None = None
    scenario_name: str | None = None
    theme: dict[str, Any] | None = None
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
    """外側のrepositoryへ保存する新規ゲームdataを表す。"""

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
    """既存ゲームへ保存できる更新内容を表す。"""

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
    """外側の永続化adapterから読み込んだゲームを表す。"""

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
    """外側の永続化adapterから読み込んだevent記録を表す。"""

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
