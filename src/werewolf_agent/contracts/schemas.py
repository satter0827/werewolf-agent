"""Public wire schemas shared by game clients."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from werewolf_agent.contracts.constants import (
    DEFAULT_NARRATION_MODE,
    MAX_CHARACTER_AGE,
    MAX_DIFFICULTY,
    MAX_HTTP_STATUS_CODE,
    MIN_CHARACTER_AGE,
    MIN_DIFFICULTY,
    MIN_HTTP_STATUS_CODE,
    MIN_PAGE_LIMIT,
    MIN_PAGE_OFFSET,
    MIN_ROLE_COUNT,
    MIN_SEQUENCE,
    MIN_VERSION,
    NarrationMode,
)
from werewolf_agent.contracts.definitions import (
    CustomCharacterDefinition,
    CustomRoleDefinition,
    LocalRulesDefinition,
)
from werewolf_agent.contracts.messages import (
    MESSAGE_CHARACTER_ASSIGNMENTS_KEYS_MUST_MATCH_PLAYERS,
    MESSAGE_CHARACTER_ASSIGNMENTS_VALUES_MUST_BE_UNIQUE,
    MESSAGE_CUSTOM_CHARACTER_IDS_MUST_BE_UNIQUE,
    MESSAGE_CUSTOM_ROLE_IDS_MUST_BE_UNIQUE,
    MESSAGE_MANUAL_PLAYER_ID_MUST_MATCH_PLAYERS,
    MESSAGE_PLAYER_COUNT_AT_LEAST_ONE,
)
from werewolf_agent.contracts.validation import (
    generated_player_ids,
    non_blank,
    optional_non_blank,
)

GAME_PHASE_NIGHT: Final = "night"
GAME_PHASE_DAY_DISCUSSION: Final = "day_discussion"
GAME_PHASE_VOTING: Final = "voting"
GAME_PHASE_FINISHED: Final = "finished"
GAME_STATUS_RUNNING: Final = "running"
GAME_STATUS_COMPLETED: Final = "completed"
ADVANCE_JOB_STATUS_QUEUED: Final = "queued"
ADVANCE_JOB_STATUS_RUNNING: Final = "running"
ADVANCE_JOB_STATUS_COMPLETED: Final = "completed"
ADVANCE_JOB_STATUS_FAILED: Final = "failed"

GamePhase = Literal["night", "day_discussion", "voting", "finished"]
GameStatus = Literal["running", "completed"]
AdvanceJobStatus = Literal["queued", "running", "completed", "failed"]
ACTIVE_ADVANCE_JOB_STATUSES: Final[frozenset[AdvanceJobStatus]] = frozenset(
    {ADVANCE_JOB_STATUS_QUEUED, ADVANCE_JOB_STATUS_RUNNING}
)
PlayerStatus = Literal["alive", "dead"]
ActionType = Literal[
    "speech",
    "vote",
    "seer_inspect",
    "knight_guard",
    "werewolf_attack",
    "pass",
]
RoleId = str
Winner = str
RoleCount = Annotated[int, Field(ge=MIN_ROLE_COUNT)]


class LocalRulesSettings(LocalRulesDefinition):
    """Local rule settings accepted when creating a game."""


class CustomRoleDefinitionRequest(CustomRoleDefinition):
    """Session-scoped role definition supplied by a UI client."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CustomCharacterDefinitionRequest(CustomCharacterDefinition):
    """Session-scoped character definition supplied by a UI client."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CreateGameRequest(BaseModel):
    """Payload for creating one game."""

    seed: int | None = None
    scenario_id: str | None = None
    setup_preset_id: str | None = None
    agent_strategy_id: str | None = None
    narration_mode: NarrationMode | None = None
    role_counts: dict[RoleId, RoleCount]
    manual_player_id: str | None = None
    rules: LocalRulesSettings | None = None
    character_assignments: dict[str, str] = Field(default_factory=dict)
    custom_roles: list[CustomRoleDefinitionRequest] = Field(default_factory=list)
    custom_characters: list[CustomCharacterDefinitionRequest] = Field(default_factory=list)

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

    @field_validator("manual_player_id")
    @classmethod
    def validate_manual_player_id(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Return a stripped optional manual player id."""
        return optional_non_blank(value, str(info.field_name))

    @field_validator("scenario_id", "setup_preset_id", "agent_strategy_id")
    @classmethod
    def validate_optional_ids(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Return stripped optional setup ids."""
        return optional_non_blank(value, str(info.field_name))

    @field_validator("character_assignments")
    @classmethod
    def validate_character_assignments(cls, value: dict[str, str]) -> dict[str, str]:
        """Return character assignments keyed by generated player id."""
        return {
            non_blank(str(player_id), "character assignment player id"): non_blank(
                character_id,
                "character assignment id",
            )
            for player_id, character_id in value.items()
        }

    @model_validator(mode="after")
    def validate_manual_player_within_generated_seats(self) -> Self:
        """Ensure the requested manual seat exists in the generated table."""
        valid_player_ids = generated_player_ids(self.player_count)
        if self.manual_player_id is not None and self.manual_player_id not in valid_player_ids:
            raise ValueError(MESSAGE_MANUAL_PLAYER_ID_MUST_MATCH_PLAYERS)
        unknown_assignments = sorted(set(self.character_assignments) - valid_player_ids)
        if unknown_assignments:
            raise ValueError(MESSAGE_CHARACTER_ASSIGNMENTS_KEYS_MUST_MATCH_PLAYERS)
        assigned_character_ids = list(self.character_assignments.values())
        if len(set(assigned_character_ids)) != len(assigned_character_ids):
            raise ValueError(MESSAGE_CHARACTER_ASSIGNMENTS_VALUES_MUST_BE_UNIQUE)
        custom_role_ids = [definition.id for definition in self.custom_roles]
        if len(set(custom_role_ids)) != len(custom_role_ids):
            raise ValueError(MESSAGE_CUSTOM_ROLE_IDS_MUST_BE_UNIQUE)
        custom_character_ids = [definition.id for definition in self.custom_characters]
        if len(set(custom_character_ids)) != len(custom_character_ids):
            raise ValueError(MESSAGE_CUSTOM_CHARACTER_IDS_MUST_BE_UNIQUE)
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
    """Public game state exposed to CLI and UI clients."""

    game_id: str
    status: GameStatus
    phase: GamePhase
    day: int
    version: int
    seed: int | None
    scenario_id: str | None = None
    scenario_name: str | None = None
    narration_mode: NarrationMode = DEFAULT_NARRATION_MODE
    players: list[PublicPlayerState]
    alive_player_ids: list[str]
    eliminated_player_ids: list[str]
    winner: Winner | None = None
    summary: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameResponse(BaseModel):
    """Response containing the current public game state."""

    game_id: str
    state: PublicGameState

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceGameResponse(BaseModel):
    """Response from advancing a game by one queued worker step."""

    game_id: str
    status: GameStatus
    state: PublicGameState
    timeline: list[GameTimelineItem]

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicGameSummary(BaseModel):
    """Public game summary for CLI and UI lists."""

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


class GameListResponse(BaseModel):
    """Public game list response."""

    games: list[PublicGameSummary]
    next_offset: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameTimelineItem(BaseModel):
    """Public timeline item shared by API, CLI, replay, and UI."""

    sequence: int = Field(ge=MIN_SEQUENCE)
    event_sequence: int = Field(ge=MIN_SEQUENCE)
    version: int = Field(ge=MIN_VERSION)
    phase: GamePhase | None = None
    day: int | None = None
    actor_id: str | None = None
    event_type: str
    narration: str | None = None
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
    """Full player state exposed only by the dedicated reveal operation."""

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
    """Pending action exposed only by the dedicated reveal operation."""

    player_id: str
    type: ActionType
    target_id: str | None = None
    message: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealInspection(BaseModel):
    """Resolved inspection exposed only by the dedicated reveal operation."""

    seer_id: str
    target_id: str
    target_role: RoleId
    target_faction: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealNight(BaseModel):
    """Resolved night record exposed only by the dedicated reveal operation."""

    day: int
    attacked_player_id: str | None = None
    protected_player_id: str | None = None
    killed_player_id: str | None = None
    inspections: list[GameRevealInspection] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealVote(BaseModel):
    """Resolved vote record exposed only by the dedicated reveal operation."""

    day: int
    votes: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    tied_player_ids: list[str] = Field(default_factory=list)
    missing_voter_ids: list[str] = Field(default_factory=list)
    eliminated_player_id: str | None = None
    tie_break_policy: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealResponse(BaseModel):
    """Full table information for admin observer UI only."""

    game_id: str
    status: GameStatus
    phase: GamePhase
    day: int
    version: int
    seed: int | None
    scenario_id: str | None = None
    scenario_name: str | None = None
    narration_mode: NarrationMode = DEFAULT_NARRATION_MODE
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


class GameListQuery(BaseModel):
    """Query parameters for listing public games."""

    status: GameStatus | None = None
    limit: int | None = Field(default=None, ge=MIN_PAGE_LIMIT)
    offset: int = Field(default=MIN_PAGE_OFFSET, ge=MIN_PAGE_OFFSET)

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameTimelineQuery(BaseModel):
    """Query parameters for reading the public game timeline."""

    after: int = Field(default=MIN_PAGE_OFFSET, ge=MIN_PAGE_OFFSET)
    limit: int | None = Field(default=None, ge=MIN_PAGE_LIMIT)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RoleDefinitionView(BaseModel):
    """Public role metadata for client bootstrapping."""

    id: str
    name: str
    faction: str
    abilities: list[str]
    description: str = ""
    difficulty: int = Field(default=MIN_DIFFICULTY, ge=MIN_DIFFICULTY, le=MAX_DIFFICULTY)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("id", "name", "faction")
    @classmethod
    def validate_non_blank(cls, value: str, info: ValidationInfo) -> str:
        """Return a stripped non-empty string."""
        return non_blank(value, str(info.field_name))


class AgentStrategyDefinitionView(BaseModel):
    """Public display metadata for an LLM agent strategy."""

    id: str
    name: str
    description: str

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("id", "name", "description")
    @classmethod
    def validate_non_blank(cls, value: str, info: ValidationInfo) -> str:
        """Return a stripped non-empty string."""
        return non_blank(value, str(info.field_name))


class GameSetupOptionsResponse(BaseModel):
    """Public setup metadata for client bootstrapping."""

    player_count: dict[str, int]
    roles: list[RoleDefinitionView]
    default_role_counts: dict[RoleId, RoleCount]
    default_rules: LocalRulesSettings
    default_scenario_id: str | None = None
    default_setup_preset_id: str | None = None
    default_narration_mode: NarrationMode = DEFAULT_NARRATION_MODE
    default_agent_strategy_id: str
    abilities: list[AbilityDefinitionView] = Field(default_factory=list)
    scenarios: list[ScenarioDefinitionView] = Field(default_factory=list)
    setup_presets: list[SetupPresetDefinitionView] = Field(default_factory=list)
    characters: list[CharacterDefinitionView] = Field(default_factory=list)
    agent_strategies: list[AgentStrategyDefinitionView] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)


class AbilityDefinitionView(BaseModel):
    """Public ability metadata for setup screens."""

    id: str
    name: str
    description: str
    target_policy: str
    difficulty: int = Field(ge=MIN_DIFFICULTY, le=MAX_DIFFICULTY)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("id", "name", "description", "target_policy")
    @classmethod
    def validate_non_blank(cls, value: str, info: ValidationInfo) -> str:
        """Return a stripped non-empty string."""
        return non_blank(value, str(info.field_name))


class ScenarioDefinitionView(BaseModel):
    """Public scenario metadata for setup screens."""

    id: str
    name: str
    summary: str
    recommended_setup_preset: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("id", "name", "summary")
    @classmethod
    def validate_non_blank(cls, value: str, info: ValidationInfo) -> str:
        """Return a stripped non-empty string."""
        return non_blank(value, str(info.field_name))


class SetupPresetDefinitionView(BaseModel):
    """Public setup preset metadata for setup screens."""

    id: str
    name: str
    scenario_id: str
    role_counts: dict[RoleId, RoleCount]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("id", "name", "scenario_id")
    @classmethod
    def validate_non_blank(cls, value: str, info: ValidationInfo) -> str:
        """Return a stripped non-empty string."""
        return non_blank(value, str(info.field_name))


class CharacterDefinitionView(BaseModel):
    """Public character metadata for setup screens."""

    id: str
    name: str
    age: int = Field(ge=MIN_CHARACTER_AGE, le=MAX_CHARACTER_AGE)
    gender: str
    personality: str
    speaking_style: str
    reasoning_style: str
    risk_tolerance: str

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator(
        "id",
        "name",
        "gender",
        "personality",
        "speaking_style",
        "reasoning_style",
        "risk_tolerance",
    )
    @classmethod
    def validate_non_blank(cls, value: str, info: ValidationInfo) -> str:
        """Return a stripped non-empty string."""
        return non_blank(value, str(info.field_name))


class PlayerObservationResponse(BaseModel):
    """Private observation visible to one authenticated player."""

    game_id: str
    player_id: str
    observation: dict[str, Any]

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerActionRequest(BaseModel):
    """One manual player action submitted through the API port."""

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
    status: int = Field(ge=MIN_HTTP_STATUS_CODE, le=MAX_HTTP_STATUS_CODE)
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


class AdvanceGameJobResponse(BaseModel):
    """Public response for a queued advance job."""

    job_id: str
    game_id: str
    status: AdvanceJobStatus
    state_version: int = Field(ge=MIN_VERSION)
    poll_url: str | None = None
    result: AdvanceGameResponse | None = None
    error: ProblemDetails | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


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
    "ACTIVE_ADVANCE_JOB_STATUSES",
    "ADVANCE_JOB_STATUS_COMPLETED",
    "ADVANCE_JOB_STATUS_FAILED",
    "ADVANCE_JOB_STATUS_QUEUED",
    "ADVANCE_JOB_STATUS_RUNNING",
    "GAME_PHASE_DAY_DISCUSSION",
    "GAME_PHASE_FINISHED",
    "GAME_PHASE_NIGHT",
    "GAME_PHASE_VOTING",
    "GAME_STATUS_COMPLETED",
    "GAME_STATUS_RUNNING",
    "AbilityDefinitionView",
    "ActionType",
    "AdvanceGameJobResponse",
    "AdvanceGameResponse",
    "AdvanceJobStatus",
    "AgentStrategyDefinitionView",
    "CharacterDefinitionView",
    "CreateGameRequest",
    "CustomCharacterDefinitionRequest",
    "CustomRoleDefinitionRequest",
    "ErrorEventPayload",
    "GameListQuery",
    "GameListResponse",
    "GamePhase",
    "GameResponse",
    "GameRevealAction",
    "GameRevealInspection",
    "GameRevealNight",
    "GameRevealPlayer",
    "GameRevealResponse",
    "GameRevealVote",
    "GameSetupOptionsResponse",
    "GameStatus",
    "GameTimelineItem",
    "GameTimelineQuery",
    "GameTimelineResponse",
    "LocalRulesSettings",
    "NarrationMode",
    "PlayerActionRequest",
    "PlayerActionResponse",
    "PlayerObservationResponse",
    "PlayerStatus",
    "ProblemDetails",
    "ProblemIssue",
    "PublicGameState",
    "PublicGameSummary",
    "PublicPlayerState",
    "RoleCount",
    "RoleDefinitionView",
    "RoleId",
    "ScenarioDefinitionView",
    "SetupPresetDefinitionView",
    "Winner",
]
