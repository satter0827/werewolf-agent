"""Use case input, output, and persistence models for game jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from werewolf_agent.commons.shared.messages import MESSAGE_PLAYER_COUNT_MUST_MATCH_PLAYERS
from werewolf_agent.commons.shared.validation import non_blank

GamePhase = Literal["night", "day_discussion", "voting", "finished"]
GameStatus = Literal["running", "completed"]
EventVisibility = Literal["public", "player_private", "debug"]
RoleId = Literal["villager", "werewolf", "seer", "knight"]
TieBreakPolicyId = Literal["no_elimination", "random_elimination"]
Winner = Literal["villagers", "werewolves"]
RoleCount = Annotated[int, Field(ge=0)]


@dataclass(frozen=True)
class GameUseCaseConfig:
    """Business settings used by stateless game jobs."""

    min_players: int = 5
    max_players: int = 8
    default_player_count: int = 6
    supported_agent_type: str = "dummy"
    default_ruleset_id: str = "default"


class _UseCaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateGamePlayer(_UseCaseModel):
    """One player requested for a new game."""

    id: str
    name: str
    agent_type: str = "dummy"

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("id", "name", "agent_type")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        """Return a stripped non-empty string."""
        return non_blank(value, "value")


class CreateGameAgentConfig(_UseCaseModel):
    """Agent selection for automated game runs."""

    type: str = "dummy"

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("type")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        """Return a stripped non-empty agent type."""
        return non_blank(value, "value")


class CreateGameRuleConfig(_UseCaseModel):
    """Rule knobs accepted when creating a game."""

    role_counts: dict[RoleId, RoleCount] | None = None
    tie_break_policy: TieBreakPolicyId = "no_elimination"
    day_speech_turns: int = Field(default=1, ge=1, le=5)
    allow_self_vote: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)


class CreateGameCommand(_UseCaseModel):
    """Command for creating one game run."""

    player_count: int | None = Field(default=None, ge=1)
    seed: int | None = None
    players: list[CreateGamePlayer] | None = None
    agent: CreateGameAgentConfig = Field(default_factory=CreateGameAgentConfig)
    rule_config: CreateGameRuleConfig = Field(default_factory=CreateGameRuleConfig)

    @model_validator(mode="after")
    def validate_players_and_count(self) -> Self:
        """Ensure player_count and explicit players describe the same table."""
        if (
            self.players is not None
            and self.player_count is not None
            and len(self.players) != self.player_count
        ):
            raise ValueError(MESSAGE_PLAYER_COUNT_MUST_MATCH_PLAYERS)
        return self


class GetGameQuery(_UseCaseModel):
    """Query for loading one game."""

    game_id: str | UUID

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceGameCommand(_UseCaseModel):
    """Command for advancing one game by one business step."""

    game_id: str | UUID

    model_config = ConfigDict(extra="forbid", frozen=True)


class ListPublicEventsQuery(_UseCaseModel):
    """Query for listing public events after a sequence cursor."""

    game_id: str | UUID
    after: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RulesetResult(_UseCaseModel):
    """Ruleset business metadata returned by use cases."""

    id: str
    player_count: dict[str, int]
    roles: list[RoleId]
    phases: list[GamePhase]
    agent_types: list[str]

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameResult(_UseCaseModel):
    """Current game state returned by use cases."""

    game_id: str
    state: dict[str, Any]

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceGameResult(_UseCaseModel):
    """Result from advancing a game by one use case step."""

    game_id: str
    status: GameStatus
    state: dict[str, Any]
    events: list[dict[str, Any]]

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicEventsResult(_UseCaseModel):
    """Public event stream returned by use cases."""

    game_id: str
    events: list[dict[str, Any]]
    next_after: int

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicPlayerState(_UseCaseModel):
    """Internal public player state projected from domain state."""

    id: str
    name: str
    alive: bool
    status: str
    eliminated_day: int | None = None
    killed_night: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicGameState(_UseCaseModel):
    """Internal public game state projected from domain state."""

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


class PublicGameEvent(_UseCaseModel):
    """Internal public event projected from a stored event record."""

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


class GameEventCreate(_UseCaseModel):
    """Sanitized event data to persist through an outer repository."""

    visibility: EventVisibility
    phase: GamePhase | None = None
    day: int | None = None
    actor_id: str | None = None
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRunCreate(_UseCaseModel):
    """New game run data to be persisted by an outer repository."""

    id: UUID
    status: GameStatus
    phase: GamePhase
    day: int
    seed: int | None
    config: dict[str, Any]
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    version: int

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRunUpdate(_UseCaseModel):
    """Persistable updates for an existing game run."""

    id: UUID
    status: GameStatus
    phase: GamePhase
    day: int
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    version: int

    model_config = ConfigDict(extra="forbid", frozen=True)


class StoredGameRun(_UseCaseModel):
    """Game run loaded from an outer persistence adapter."""

    id: UUID
    status: GameStatus
    phase: GamePhase
    day: int
    seed: int | None
    config: dict[str, Any]
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


class StoredGameEvent(_UseCaseModel):
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
