"""Public wire schemas shared by game clients."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationInfo, field_validator

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


class DiscussionStageSettings(BaseModel):
    """一つの議論stageを表すwire設定."""

    stage: Literal["opening", "response"]
    submission_mode: Literal["sealed", "ordered"]
    actor_order: Literal["rotating", "reverse_opening"]
    allowed_relations: tuple[
        Literal["independent", "answer", "support", "challenge", "revise"], ...
    ]
    reference_stage: Literal["opening"] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

    model_config = ConfigDict(extra="forbid", frozen=True)


class DiscussionSettings(BaseModel):
    """議論protocolのwire設定."""

    protocol_id: Literal["structured_argument"]
    message_max_chars: int = Field(ge=1, le=2000)
    cycles_per_day: int = Field(default=1, ge=1, le=10)
    stages: tuple[DiscussionStageSettings, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)


class VotingSettings(BaseModel):
    """投票のwire設定."""

    allow_self_vote: bool
    allow_revision: bool
    tie_resolution: Literal["no_elimination", "random_elimination", "revote"]
    reason_max_chars: int = Field(ge=1, le=1000)

    model_config = ConfigDict(extra="forbid", frozen=True)


class NightSettings(BaseModel):
    """夜行動のwire設定."""

    allow_action_revision: bool
    allow_pass: bool

    model_config = ConfigDict(extra="forbid", frozen=True)


class LifecycleSettings(BaseModel):
    """phase遷移のwire設定."""

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
    discussion: DiscussionSettings
    voting: VotingSettings
    night: NightSettings
    lifecycle: LifecycleSettings

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

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicPersonaSettings(BaseModel):
    personality: str
    speaking_style: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class PrivateStrategySettings(BaseModel):
    reasoning_style: str
    risk_tolerance: Literal["low", "medium", "high"]
    evidence_focus: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerGenerationSettings(BaseModel):
    identities: tuple[PlayerIdentitySettings, ...]
    public_personas: tuple[PublicPersonaSettings, ...]
    private_strategies: tuple[PrivateStrategySettings, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameSetupDocumentRequest(BaseModel):
    schema_version: Literal["0.6.0"]
    mechanics: SetupMechanicsSettings
    theme: StoryThemeSettings
    player_generation: PlayerGenerationSettings

    model_config = ConfigDict(extra="forbid", frozen=True)


class TemplateSetupRequest(BaseModel):
    mode: Literal["template"]
    template_id: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class SavedSetupRequest(BaseModel):
    mode: Literal["saved"]
    setup_id: str
    revision: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class InlineSetupRequest(BaseModel):
    mode: Literal["inline"]
    document: GameSetupDocumentRequest

    model_config = ConfigDict(extra="forbid", frozen=True)


GameSetupSelectionRequest = Annotated[
    TemplateSetupRequest | SavedSetupRequest | InlineSetupRequest,
    Field(discriminator="mode"),
]


class CreateGameRequest(BaseModel):
    """Payload for creating one game."""

    seed: int | None = Field(default=None, description="Public roster reproduction seed.")
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
    utterance: str | None = None
    reason: str | None = None
    topic_id: str | None = None
    position: Literal["support", "oppose", "undecided"] | None = None
    relation: Literal["independent", "answer", "support", "challenge", "revise"] | None = None
    evidence_id: str | None = None
    response_to_id: str | None = None

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
    reasons: dict[str, str] = Field(default_factory=dict)
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
    discussion: DiscussionSettings
    voting: VotingSettings
    night: NightSettings
    lifecycle: LifecycleSettings
    players: list[GameRevealPlayer]
    alive_player_ids: list[str]
    eliminated_player_ids: list[str]
    winner: Winner | None = None
    pending_votes: list[GameRevealAction] = Field(default_factory=list)
    pending_night_actions: list[GameRevealAction] = Field(default_factory=list)
    pending_discussion_actions: list[GameRevealAction] = Field(default_factory=list)
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


class PlayerObservationPlayer(BaseModel):
    """One player as visible to the authenticated observer."""

    id: str
    name: str
    status: PlayerStatus
    role: str | None = None
    eliminated_day: int | None = None
    killed_night: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceFactDescriptor(BaseModel):
    """One server-authorized public fact that may ground an action."""

    evidence_id: str
    kind: Literal["discussion", "discussion_pass"]
    actor_id: str
    topic_id: str
    position: Literal["support", "oppose", "undecided"] | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class AvailableActionDescriptor(BaseModel):
    """One legal action and its server-authorized target candidates."""

    key: str
    type: ActionType
    ability_id: str | None = None
    legal_target_ids: list[str] = Field(default_factory=list)
    evidence_options: list[EvidenceFactDescriptor] = Field(default_factory=list)
    message_required: bool = False
    message_max_chars: int | None = Field(default=None, ge=1, le=2000)
    reason_max_chars: int | None = Field(default=None, ge=1, le=1000)

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerObservationSpeech(BaseModel):
    """One public speech visible in a player observation."""

    day: int = Field(ge=1)
    speech_id: str
    round_id: str
    round_kind: Literal["opening", "response"]
    player_id: str
    utterance: str
    topic_id: str
    position: Literal["support", "oppose", "undecided"]
    relation: Literal["independent", "answer", "support", "challenge", "revise"]
    evidence_id: str | None = None
    response_to_id: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerObservationVote(BaseModel):
    """One resolved public vote round visible in a player observation."""

    day: int = Field(ge=1)
    tie_break_policy: str
    votes: dict[str, str] = Field(default_factory=dict)
    reasons: dict[str, str] = Field(default_factory=dict)
    evidence_ids: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    tied_player_ids: list[str] = Field(default_factory=list)
    missing_voter_ids: list[str] = Field(default_factory=list)
    eliminated_player_id: str | None = None
    round: int = Field(default=1, ge=1)
    requires_revote: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerObservationHistory(BaseModel):
    """Public history included in one player observation."""

    speeches: list[PlayerObservationSpeech] = Field(default_factory=list)
    votes: list[PlayerObservationVote] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)


class DiscussionResponseOptionDescriptor(BaseModel):
    """Serverが許可する一つのresponse構造候補を表す."""

    response_to_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    topic_id: str = Field(min_length=1)
    position: Literal["support", "oppose", "undecided"]
    relation: Literal["answer", "support", "challenge", "revise"]

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class DiscussionRoundDescriptor(BaseModel):
    """Playerへ公開できる現在の議論roundを表す."""

    round_id: str
    cycle: int = Field(ge=1)
    kind: Literal["opening", "response"]
    submission_mode: Literal["sealed", "ordered"]
    actor_order: list[str]
    cursor: int = Field(ge=0)
    reference_ids: list[str] = Field(default_factory=list)
    allowed_relations: list[Literal["independent", "answer", "support", "challenge", "revise"]] = (
        Field(default_factory=list)
    )
    response_options: list[DiscussionResponseOptionDescriptor] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerObservationOutcome(BaseModel):
    """Public game outcome without hidden winning player identities."""

    winner: Winner
    reason: str
    day: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerObservation(BaseModel):
    """Typed private observation used to build an independent game client."""

    phase: GamePhase
    day: int = Field(ge=1)
    me: PlayerObservationPlayer
    players: list[PlayerObservationPlayer]
    known_roles: dict[str, str] = Field(default_factory=dict)
    known_factions: dict[str, Winner] = Field(default_factory=dict)
    available_actions: list[AvailableActionDescriptor] = Field(default_factory=list)
    history: PlayerObservationHistory = Field(default_factory=PlayerObservationHistory)
    discussion_round: DiscussionRoundDescriptor | None = None
    win_result: PlayerObservationOutcome | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerObservationResponse(BaseModel):
    """Private observation visible to one authenticated player."""

    game_id: str
    player_id: str
    observation: PlayerObservation

    model_config = ConfigDict(extra="forbid", frozen=True)


class SpeechActionRequest(BaseModel):
    """公開発言request."""

    type: Literal["speech"]
    utterance: str = Field(min_length=1)
    topic_id: str = Field(min_length=1)
    position: Literal["support", "oppose", "undecided"]
    relation: Literal["independent", "answer", "support", "challenge", "revise"]
    evidence_id: str | None = Field(default=None, min_length=1)
    response_to_id: str | None = Field(default=None, min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class VoteActionRequest(BaseModel):
    """公開理由付き投票request."""

    type: Literal["vote"]
    target_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evidence_id: str | None = Field(default=None, min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class UseAbilityActionRequest(BaseModel):
    """能力使用request."""

    type: Literal["use_ability"]
    ability_id: str = Field(min_length=1)
    target_id: str | None = Field(default=None, min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class PassActionRequest(BaseModel):
    """行動しないrequest."""

    type: Literal["pass"]

    model_config = ConfigDict(extra="forbid", frozen=True)


PlayerActionRequest = Annotated[
    SpeechActionRequest | VoteActionRequest | UseAbilityActionRequest | PassActionRequest,
    Field(discriminator="type"),
]
PLAYER_ACTION_REQUEST_ADAPTER: TypeAdapter[PlayerActionRequest] = TypeAdapter(PlayerActionRequest)


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
    "PLAYER_ACTION_REQUEST_ADAPTER",
    "ActionType",
    "AdvanceGameJobResponse",
    "AdvanceGameResponse",
    "AdvanceJobStatus",
    "AvailableActionDescriptor",
    "CreateGameRequest",
    "DeliberationLevel",
    "DiscussionResponseOptionDescriptor",
    "DiscussionRoundDescriptor",
    "DiscussionSettings",
    "ErrorEventPayload",
    "EvidenceFactDescriptor",
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
    "LifecycleSettings",
    "NarrationMode",
    "NightSettings",
    "PassActionRequest",
    "PlayerActionRequest",
    "PlayerActionResponse",
    "PlayerObservation",
    "PlayerObservationHistory",
    "PlayerObservationOutcome",
    "PlayerObservationPlayer",
    "PlayerObservationResponse",
    "PlayerObservationSpeech",
    "PlayerObservationVote",
    "PlayerStatus",
    "ProblemDetails",
    "ProblemIssue",
    "PublicGameState",
    "PublicGameSummary",
    "PublicPlayerState",
    "RecoveryAction",
    "RoleCount",
    "RoleId",
    "SpeechActionRequest",
    "UseAbilityActionRequest",
    "VoteActionRequest",
    "VotingSettings",
    "Winner",
]
