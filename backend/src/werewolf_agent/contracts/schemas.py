"""Public wire schemas shared by API, CUI, and future UI entry points."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from werewolf_agent.commons.shared.definitions import LocalRulesDefinition
from werewolf_agent.commons.shared.messages import MESSAGE_PLAYER_COUNT_AT_LEAST_ONE
from werewolf_agent.commons.shared.validation import non_blank, optional_non_blank

GamePhase = Literal["night", "day_discussion", "voting", "finished"]
GameStatus = Literal["running", "completed"]
PlayerStatus = Literal["alive", "dead"]
ActionType = str
RoleId = str
Winner = Literal["villagers", "werewolves"]
AdvanceUntilInputStopReason = Literal["manual_input_required", "completed", "hit_limit"]
RoleCount = Annotated[int, Field(ge=0)]


class LocalRulesSettings(LocalRulesDefinition):
    """Local rule settings accepted when creating a game."""


class CreateGameRequest(BaseModel):
    """Payload for creating one game."""

    seed: int | None = None
    role_counts: dict[RoleId, RoleCount]
    human_player_id: str | None = None
    rules: LocalRulesSettings | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("role_counts")
    @classmethod
    def validate_role_counts(cls, value: dict[RoleId, RoleCount]) -> dict[RoleId, RoleCount]:
        """Return role counts keyed by normalized role id."""
        normalized = {
            non_blank(str(role_id), "role_counts key"): count for role_id, count in value.items()
        }
        if sum(normalized.values()) < 1:
            raise ValueError(MESSAGE_PLAYER_COUNT_AT_LEAST_ONE)
        return normalized

    @field_validator("human_player_id")
    @classmethod
    def validate_human_player_id(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Return a stripped optional human player id."""
        return optional_non_blank(value, str(info.field_name))

    @model_validator(mode="after")
    def validate_human_player_within_generated_seats(self) -> Self:
        """Ensure the requested human seat exists in the generated table."""
        if self.human_player_id is None:
            return self
        valid_player_ids = {f"player-{index}" for index in range(1, self.player_count + 1)}
        if self.human_player_id not in valid_player_ids:
            raise ValueError("human_player_id must match a generated player id")
        return self

    @property
    def player_count(self) -> int:
        """Return the player count derived from role counts."""
        return sum(self.role_counts.values())


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


class AdvanceUntilInputResponse(BaseModel):
    """Response from advancing until manual input, completion, or configured limit."""

    game_id: str
    status: GameStatus
    state: PublicGameState
    timeline: list[GameTimelineItem]
    stop_reason: AdvanceUntilInputStopReason
    steps: int

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


class GameRevealPlayer(BaseModel):
    """Full player state exposed only by the dedicated reveal API."""

    id: str
    name: str
    role: RoleId
    faction: str
    alive: bool
    status: PlayerStatus
    eliminated_day: int | None = None
    killed_night: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealAction(BaseModel):
    """Pending action exposed only by the dedicated reveal API."""

    player_id: str
    type: ActionType
    target_id: str | None = None
    message: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealInspection(BaseModel):
    """Resolved inspection exposed only by the dedicated reveal API."""

    seer_id: str
    target_id: str
    target_role: RoleId
    target_faction: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealNight(BaseModel):
    """Resolved night record exposed only by the dedicated reveal API."""

    day: int
    attacked_player_id: str | None = None
    protected_player_id: str | None = None
    killed_player_id: str | None = None
    inspections: list[GameRevealInspection] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealVote(BaseModel):
    """Resolved vote record exposed only by the dedicated reveal API."""

    day: int
    votes: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    tied_player_ids: list[str] = Field(default_factory=list)
    missing_voter_ids: list[str] = Field(default_factory=list)
    eliminated_player_id: str | None = None
    tie_break_policy: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealResponse(BaseModel):
    """Full table information for local observer/demo UI only."""

    game_id: str
    status: GameStatus
    phase: GamePhase
    day: int
    version: int
    seed: int | None
    role_counts: dict[RoleId, RoleCount]
    rules: LocalRulesSettings
    players: list[GameRevealPlayer]
    alive_player_ids: list[str]
    eliminated_player_ids: list[str]
    winner: Winner | None = None
    pending_votes: list[GameRevealAction] = Field(default_factory=list)
    pending_night_actions: list[GameRevealAction] = Field(default_factory=list)
    votes: list[GameRevealVote] = Field(default_factory=list)
    nights: list[GameRevealNight] = Field(default_factory=list)

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


class RoleDefinitionView(BaseModel):
    """Public role metadata for client bootstrapping."""

    id: str
    name: str
    faction: str
    abilities: list[str]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("id", "name", "faction")
    @classmethod
    def validate_non_blank(cls, value: str, info: ValidationInfo) -> str:
        """Return a stripped non-empty string."""
        return non_blank(value, str(info.field_name))


class RulesetResponse(BaseModel):
    """Public ruleset metadata for client bootstrapping."""

    player_count: dict[str, int]
    roles: list[RoleDefinitionView]
    default_role_counts: dict[RoleId, RoleCount]
    default_rules: LocalRulesSettings

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
    "AdvanceUntilInputResponse",
    "CreateGameRequest",
    "ErrorEventPayload",
    "GamePhase",
    "GameRevealAction",
    "GameRevealInspection",
    "GameRevealNight",
    "GameRevealPlayer",
    "GameRevealResponse",
    "GameRevealVote",
    "GameRunResponse",
    "GameRunsQuery",
    "GameRunsResponse",
    "GameStatus",
    "GameTimelineItem",
    "GameTimelineQuery",
    "GameTimelineResponse",
    "LocalRulesSettings",
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
    "RoleDefinitionView",
    "RoleId",
    "RulesetResponse",
    "Winner",
]
