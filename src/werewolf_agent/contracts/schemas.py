"""Public wire schemas shared by game clients."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from werewolf_agent.contracts.constants import (
    DEFAULT_DELIBERATION_LEVEL,
    DEFAULT_NARRATION_MODE,
    MAX_HTTP_STATUS_CODE,
    MIN_HTTP_STATUS_CODE,
    MIN_PAGE_LIMIT,
    MIN_PAGE_OFFSET,
    MIN_ROLE_COUNT,
    MIN_SEQUENCE,
    MIN_VERSION,
    DeliberationLevel,
    NarrationMode,
)
from werewolf_agent.contracts.validation import (
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
RecoveryAction = Literal[
    "retry",
    "sign_in",
    "reload",
    "check_configuration",
    "contact_admin",
    "none",
]
ACTIVE_ADVANCE_JOB_STATUSES: Final[frozenset[AdvanceJobStatus]] = frozenset(
    {ADVANCE_JOB_STATUS_QUEUED, ADVANCE_JOB_STATUS_RUNNING}
)
PlayerStatus = Literal["alive", "dead"]
ActionType = Literal[
    "speech",
    "vote",
    "use_ability",
    "pass",
]
RoleId = str
Winner = Literal["village", "werewolf", "fox"]
RoleCount = Annotated[int, Field(ge=MIN_ROLE_COUNT)]
SetupRoleCount = Annotated[int, Field(ge=1)]


class LocalRulesSettings(BaseModel):
    """Complete mutable game rules carried by an inline setup."""

    day_speech_limit_per_player: int = Field(ge=0, le=100)
    allow_self_vote: bool
    allow_vote_revision: bool
    allow_night_action_revision: bool
    vote_tie_resolution: Literal["no_elimination", "random_elimination", "revote"]
    starting_phase: Literal["night", "day_discussion"]
    reveal_role_on_death: bool
    require_all_actions_before_advance: bool

    model_config = ConfigDict(extra="forbid", frozen=True)


class SetupRoleDefinition(BaseModel):
    identity_faction: Winner
    victory_team: Winner
    abilities: tuple[str, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)


class SetupAbilityComponent(BaseModel):
    kind: str
    phase: Literal["night", "day_discussion", "voting", "finished"]
    target_policy: Literal["none", "alive", "other_alive", "other_alive_non_faction"]
    start_day: int = Field(ge=1)
    max_uses: Literal["unlimited"] | Annotated[int, Field(ge=1)]
    result_visibility: Literal["private", "public", "none"]
    resolution_priority: int = Field(ge=0, le=1000)
    allow_repeat_target: bool
    enabled_first_night: bool

    model_config = ConfigDict(extra="forbid", frozen=True)


class SetupAttackAbility(SetupAbilityComponent):
    kind: Literal["attack"]
    tie_resolution: Literal["random_target", "no_action"]


class SetupInspectAbility(SetupAbilityComponent):
    kind: Literal["inspect"]
    result_detail: Literal["faction", "role"]


class SetupProtectAbility(SetupAbilityComponent):
    kind: Literal["protect"]


class SetupEliminateAbility(SetupAbilityComponent):
    kind: Literal["eliminate"]


class SetupKnowledgeAbility(SetupAbilityComponent):
    kind: Literal["knowledge"]
    knowledge_mode: Literal["allies", "last_eliminated"]
    result_detail: Literal["faction", "role"]


class SetupDeathReactionAbility(SetupAbilityComponent):
    kind: Literal["death_reaction"]


class SetupImmunityAbility(SetupAbilityComponent):
    kind: Literal["immunity"]
    source_kinds: Annotated[
        tuple[Literal["attack", "eliminate", "inspect"], ...],
        Field(min_length=1),
    ]


class SetupVulnerabilityAbility(SetupAbilityComponent):
    kind: Literal["vulnerability"]
    source_kinds: Annotated[tuple[Literal["inspect"], ...], Field(min_length=1)]


SetupAbilityDefinition = Annotated[
    SetupAttackAbility
    | SetupInspectAbility
    | SetupProtectAbility
    | SetupEliminateAbility
    | SetupKnowledgeAbility
    | SetupDeathReactionAbility
    | SetupImmunityAbility
    | SetupVulnerabilityAbility,
    Field(discriminator="kind"),
]


class SetupMechanicsSettings(BaseModel):
    role_counts: dict[str, SetupRoleCount]
    roles: dict[str, SetupRoleDefinition]
    abilities: dict[str, SetupAbilityDefinition]
    rules: LocalRulesSettings

    model_config = ConfigDict(extra="forbid", frozen=True)


class StoryThemeSettings(BaseModel):
    id: str
    name: str
    summary: str
    premise: str
    role_names: dict[str, str]
    role_objectives: dict[str, str]
    role_descriptions: dict[str, str]
    faction_names: dict[str, str]
    ability_names: dict[str, str]
    ability_descriptions: dict[str, str]
    action_names: dict[str, str]
    phase_names: dict[str, str]
    narration_enabled: bool
    narration: dict[str, tuple[str, ...]]

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerIdentitySettings(BaseModel):
    name: str
    age_min: int = Field(ge=18, le=120)
    age_max: int = Field(ge=18, le=120)
    gender: str


class PublicPersonaSettings(BaseModel):
    personality: str
    speaking_style: str


class PrivateStrategySettings(BaseModel):
    reasoning_style: str
    risk_tolerance: Literal["low", "medium", "high"]
    evidence_focus: str


class PlayerGenerationSettings(BaseModel):
    identities: tuple[PlayerIdentitySettings, ...]
    public_personas: tuple[PublicPersonaSettings, ...]
    private_strategies: tuple[PrivateStrategySettings, ...]


class GameSetupDocumentRequest(BaseModel):
    schema_version: Literal[2]
    mechanics: SetupMechanicsSettings
    theme: StoryThemeSettings
    player_generation: PlayerGenerationSettings

    model_config = ConfigDict(extra="forbid", frozen=True)


class TemplateSetupRequest(BaseModel):
    mode: Literal["template"]
    template_id: str


class SavedSetupRequest(BaseModel):
    mode: Literal["saved"]
    setup_id: str
    revision: int = Field(ge=1)


class InlineSetupRequest(BaseModel):
    mode: Literal["inline"]
    document: GameSetupDocumentRequest


GameSetupSelectionRequest = Annotated[
    TemplateSetupRequest | SavedSetupRequest | InlineSetupRequest,
    Field(discriminator="mode"),
]


class CreateGameRequest(BaseModel):
    """Payload for creating one game."""

    seed: int | None = None
    setup: GameSetupSelectionRequest
    manual_player_id: str | None = None
    deliberation_level: DeliberationLevel = DEFAULT_DELIBERATION_LEVEL

    model_config = ConfigDict(extra="forbid")

    @field_validator("manual_player_id")
    @classmethod
    def validate_manual_player_id(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Return a stripped optional manual player id."""
        return optional_non_blank(value, str(info.field_name))


class PublicPlayerState(BaseModel):
    """Public player state exposed to clients."""

    id: str
    name: str
    alive: bool
    status: PlayerStatus
    eliminated_day: int | None = None
    killed_night: int | None = None
    role: str | None = None
    faction: Literal["village", "werewolf", "fox"] | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicTheme(BaseModel):
    """Presentation terms selected for one game."""

    id: str
    name: str
    premise: str
    role_names: dict[str, str]
    role_objectives: dict[str, str]
    faction_names: dict[str, str]
    ability_names: dict[str, str]
    action_names: dict[str, str]
    phase_names: dict[str, str]

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
    theme: PublicTheme | None = None
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
    scenario_id: str | None = None
    scenario_name: str | None = None
    theme: PublicTheme | None = None
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
    identity_faction: str
    victory_team: str
    objective: str
    alive: bool
    status: PlayerStatus
    eliminated_day: int | None = None
    killed_night: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealAction(BaseModel):
    """Pending action exposed only by the dedicated reveal operation."""

    player_id: str
    type: ActionType
    ability_id: str | None = None
    target_id: str | None = None
    message: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealInspection(BaseModel):
    """Resolved inspection exposed only by the dedicated reveal operation."""

    player_id: str
    ability_id: str
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


class PlayerObservationResponse(BaseModel):
    """Private observation visible to one authenticated player."""

    game_id: str
    player_id: str
    observation: dict[str, Any]

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerActionRequest(BaseModel):
    """One manual player action submitted through the API port."""

    type: ActionType
    ability_id: str | None = None
    target_id: str | None = None
    message: str | None = None
    reason: str = ""

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("ability_id", "target_id", "message")
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
    retryable: bool = False
    recovery: RecoveryAction = "none"

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
    "ActionType",
    "AdvanceGameJobResponse",
    "AdvanceGameResponse",
    "AdvanceJobStatus",
    "CreateGameRequest",
    "DeliberationLevel",
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
    "RecoveryAction",
    "RoleCount",
    "RoleId",
    "Winner",
]
