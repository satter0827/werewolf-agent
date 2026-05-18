"""Public API schemas shared by HTTP handlers and API clients."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

GamePhase = Literal["night", "day_discussion", "voting", "finished"]
GameStatus = Literal["running", "completed"]
RoleId = Literal["villager", "werewolf", "seer", "knight"]
TieBreakPolicyId = Literal["no_elimination", "random_elimination"]
Winner = Literal["villagers", "werewolves"]
RoleCount = Annotated[int, Field(ge=0)]


class CreateGamePlayer(BaseModel):
    """One player in a create-game request."""

    id: str
    name: str
    agent_type: str = "dummy"

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("id", "name", "agent_type")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        """Return a stripped non-empty string."""
        normalized = value.strip()
        if not normalized:
            msg = "value must not be blank"
            raise ValueError(msg)
        return normalized


class CreateGameAgentConfig(BaseModel):
    """Agent selection for MVP API-driven game runs."""

    type: str = "dummy"

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("type")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        """Return a stripped non-empty agent type."""
        normalized = value.strip()
        if not normalized:
            msg = "value must not be blank"
            raise ValueError(msg)
        return normalized


class CreateGameRuleConfig(BaseModel):
    """Rule knobs accepted by the MVP create-game endpoint."""

    role_counts: dict[RoleId, RoleCount] | None = None
    tie_break_policy: TieBreakPolicyId = "no_elimination"
    day_speech_turns: int = Field(default=1, ge=1, le=5)
    allow_self_vote: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)


class CreateGameRequest(BaseModel):
    """Payload for creating one game."""

    player_count: int | None = Field(default=None, ge=5, le=8)
    seed: int | None = None
    players: list[CreateGamePlayer] | None = None
    agent: CreateGameAgentConfig = Field(default_factory=CreateGameAgentConfig)
    rule_config: CreateGameRuleConfig = Field(default_factory=CreateGameRuleConfig)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_players_and_count(self) -> Self:
        """Ensure player_count and explicit players describe the same table."""
        if (
            self.players is not None
            and self.player_count is not None
            and len(self.players) != self.player_count
        ):
            msg = "player_count must match the number of players"
            raise ValueError(msg)
        return self

    @property
    def resolved_player_count(self) -> int:
        """Return the requested player count, defaulting to the MVP table size."""
        if self.players is not None:
            return len(self.players)
        if self.player_count is not None:
            return self.player_count
        return 6


class PublicPlayerState(BaseModel):
    """Public player state exposed to clients."""

    id: str
    name: str
    alive: bool
    status: str
    eliminated_day: int | None = None
    killed_night: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicGameState(BaseModel):
    """Public game state exposed to CLI and future UI clients."""

    game_id: str
    status: GameStatus
    phase: GamePhase
    day: int
    version: int
    seed: int | None
    players: list[PublicPlayerState]
    alive_player_ids: list[str]
    eliminated_player_ids: list[str]
    winner: Winner | None = None
    summary: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicGameEvent(BaseModel):
    """One public event in the API event stream."""

    sequence: int = Field(ge=1)
    event_id: UUID
    event_type: str
    phase: GamePhase | None = None
    day: int | None = None
    actor_id: str | None = None
    visibility: Literal["public"] = "public"
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameResponse(BaseModel):
    """Response containing the current public game state."""

    game_id: str
    state: PublicGameState

    model_config = ConfigDict(extra="forbid", frozen=True)


class StepGameResponse(BaseModel):
    """Response from advancing a game by one API-side step."""

    game_id: str
    status: GameStatus
    state: PublicGameState
    events: list[PublicGameEvent]

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameEventsQuery(BaseModel):
    """Query parameters for listing public events."""

    after: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid")


class GameEventsResponse(BaseModel):
    """Public event stream response."""

    game_id: str
    events: list[PublicGameEvent]
    next_after: int

    model_config = ConfigDict(extra="forbid", frozen=True)


class RulesetResponse(BaseModel):
    """Public ruleset metadata for client bootstrapping."""

    id: str
    name: str
    description: str
    player_count: dict[str, int]
    roles: list[dict[str, str]]
    phases: list[dict[str, str]]
    agent_types: list[dict[str, str]]

    model_config = ConfigDict(extra="forbid", frozen=True)
