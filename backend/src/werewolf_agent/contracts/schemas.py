"""Public wire schemas shared by API, CUI, and future UI entry points."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from werewolf_agent.commons.shared.messages import MESSAGE_PLAYER_COUNT_MUST_MATCH_PLAYERS
from werewolf_agent.commons.shared.validation import non_blank, optional_non_blank

GamePhase = Literal["night", "day_discussion", "voting", "finished"]
GameStatus = Literal["running", "completed"]
PlayerStatus = Literal["alive", "dead"]
ActionType = Literal["speech", "vote", "werewolf_attack", "seer_inspect", "knight_guard", "pass"]
RoleId = Literal["villager", "werewolf", "seer", "knight"]
TieBreakPolicyId = Literal["no_elimination", "random_elimination"]
Winner = Literal["villagers", "werewolves"]
RoleCount = Annotated[int, Field(ge=0)]


class CreateGamePlayer(BaseModel):
    """One player in a create-game request."""

    id: str
    name: str
    agent_type: str = "llm"

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("id", "name", "agent_type")
    @classmethod
    def validate_non_blank(cls, value: str, info: ValidationInfo) -> str:
        """Return a stripped non-empty string."""
        return non_blank(value, str(info.field_name))


class CreateGameAgentConfig(BaseModel):
    """Agent selection for API-driven game runs."""

    type: str = "llm"

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("type")
    @classmethod
    def validate_non_blank(cls, value: str, info: ValidationInfo) -> str:
        """Return a stripped non-empty agent type."""
        return non_blank(value, str(info.field_name))


class CreateGameRuleConfig(BaseModel):
    """Rule knobs accepted by the create-game endpoint."""

    role_counts: dict[RoleId, RoleCount] | None = None
    tie_break_policy: TieBreakPolicyId = "no_elimination"
    day_speech_turns: int = Field(default=1, ge=1, le=5)
    allow_self_vote: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)


class CreateGameRunRequest(BaseModel):
    """Payload for creating one game."""

    player_count: int | None = Field(default=None, ge=1)
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
            raise ValueError(MESSAGE_PLAYER_COUNT_MUST_MATCH_PLAYERS)
        return self


class PublicPlayerState(BaseModel):
    """Public player state exposed to clients."""

    id: str
    name: str
    alive: bool
    status: PlayerStatus
    eliminated_day: int | None = None
    killed_night: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicGameState(BaseModel):
    """Public game state exposed to CUI and future UI clients."""

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


class GameRunResponse(BaseModel):
    """Response containing the current public game state."""

    game_id: str
    state: PublicGameState
    control_tokens: dict[str, str] | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceGameRunResponse(BaseModel):
    """Response from advancing a game by one API-side step."""

    game_id: str
    status: GameStatus
    state: PublicGameState
    timeline: list[GameTimelineItem]

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicGameRunSummary(BaseModel):
    """Public run summary for CLI and future UI lists."""

    game_id: str
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


class GameRunsResponse(BaseModel):
    """Public run list response."""

    runs: list[PublicGameRunSummary]
    next_offset: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameTimelineItem(BaseModel):
    """Public timeline item shared by API, CLI, replay, SSE, and UI."""

    sequence: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    version: int = Field(ge=1)
    phase: GamePhase | None = None
    day: int | None = None
    actor_id: str | None = None
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameTimelineResponse(BaseModel):
    """Public game timeline response."""

    game_id: str
    items: list[GameTimelineItem]
    next_after: int

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRunsQuery(BaseModel):
    """Query parameters for listing public runs."""

    status: GameStatus | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameTimelineQuery(BaseModel):
    """Query parameters for reading the public game timeline."""

    after: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=500)

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


class PlayerObservationResponse(BaseModel):
    """Private observation visible to one authenticated player."""

    game_id: str
    player_id: str
    observation: dict[str, Any]

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerActionRequest(BaseModel):
    """One manual player action submitted through the API."""

    type: ActionType
    target_id: str | None = None
    message: str | None = None
    reason: str = ""

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("target_id", "message")
    @classmethod
    def validate_optional_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Return stripped optional action text."""
        return optional_non_blank(value, str(info.field_name))

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        """Return stripped optional action reason text."""
        return value.strip()


class PlayerActionResponse(BaseModel):
    """Response after accepting a manual action."""

    game_id: str
    player_id: str
    state: PublicGameState
    timeline: list[GameTimelineItem]

    model_config = ConfigDict(extra="forbid", frozen=True)


class ProblemIssue(BaseModel):
    """One validation issue in an RFC 9457 Problem Details response."""

    code: str
    detail: str
    pointer: str = ""

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("code", "detail")
    @classmethod
    def validate_non_blank(cls, value: str, info: ValidationInfo) -> str:
        """Return stripped non-empty problem issue text."""
        return non_blank(value, str(info.field_name))


class ProblemDetails(BaseModel):
    """RFC 9457 Problem Details response body with project extensions."""

    type: str
    title: str
    status: int = Field(ge=100, le=599)
    detail: str
    instance: str
    code: str
    trace_id: str | None = None
    errors: list[ProblemIssue] | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("type", "title", "detail", "instance", "code")
    @classmethod
    def validate_non_blank(cls, value: str, info: ValidationInfo) -> str:
        """Return stripped non-empty problem detail text."""
        return non_blank(value, str(info.field_name))


class ErrorEventPayload(BaseModel):
    """Replay-safe JSONL payload for an application error event."""

    code: str
    detail: str
    retryable: bool
    context: dict[str, Any] | None = Field(default=None)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("code", "detail")
    @classmethod
    def validate_non_blank(cls, value: str, info: ValidationInfo) -> str:
        """Return stripped non-empty error event text."""
        return non_blank(value, str(info.field_name))


__all__ = [
    "ActionType",
    "AdvanceGameRunResponse",
    "CreateGameAgentConfig",
    "CreateGamePlayer",
    "CreateGameRuleConfig",
    "CreateGameRunRequest",
    "ErrorEventPayload",
    "GamePhase",
    "GameRunResponse",
    "GameRunsQuery",
    "GameRunsResponse",
    "GameStatus",
    "GameTimelineItem",
    "GameTimelineQuery",
    "GameTimelineResponse",
    "PlayerActionRequest",
    "PlayerActionResponse",
    "PlayerObservationResponse",
    "PlayerStatus",
    "ProblemDetails",
    "ProblemIssue",
    "PublicGameRunSummary",
    "PublicGameState",
    "PublicPlayerState",
    "RoleCount",
    "RoleId",
    "RulesetResponse",
    "TieBreakPolicyId",
    "Winner",
]
