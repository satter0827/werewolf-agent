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
    MESSAGE_MANUAL_PLAYER_ID_MUST_MATCH_PLAYERS,
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
    "seer_inspect",
    "knight_guard",
    "werewolf_attack",
    "apothecary_heal",
    "apothecary_poison",
    "pass",
]
RoleId = str
Winner = Literal["village", "werewolf", "fox"]
RoleCount = Annotated[int, Field(ge=MIN_ROLE_COUNT)]


class LocalRulesSettings(LocalRulesDefinition):
    """Local rule settings accepted when creating a game."""


class CustomRoleDefinitionRequest(CustomRoleDefinition):
    """Session-scoped role definition supplied by a UI client."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CustomCharacterDefinitionRequest(CustomCharacterDefinition):
    """Session-scoped character definition supplied by a UI client."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SetupAbilityDefinition(BaseModel):
    """Wire definition for one registered, typed ability."""

    phase: str
    action: str
    validation_policy: str
    resolution_policy: str
    target_policy: str
    effect: Literal[
        "attack",
        "inspection",
        "protection",
        "poison",
        "knowledge",
        "reaction",
        "immunity",
        "vulnerability",
        "pass",
    ]
    start_day: int = Field(ge=1)
    label: str
    description: str
    difficulty: int = Field(default=1, ge=1, le=5)
    max_uses: int | None = Field(default=None, ge=1)
    result_visibility: Literal["private", "public", "none"] = "private"
    resolution_priority: int = Field(default=100, ge=0, le=1000)

    model_config = ConfigDict(extra="forbid", frozen=True)


class SetupRoleDefinition(BaseModel):
    """Wire definition for one stable role ID."""

    identity_faction: Literal["village", "werewolf", "fox"]
    victory_team: Literal["village", "werewolf", "fox"]
    objective: str
    abilities: tuple[str, ...] = ()
    label: str
    description: str
    difficulty: int = Field(default=1, ge=1, le=5)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("abilities")
    @classmethod
    def validate_abilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Normalize ability IDs and reject ambiguous duplicate references."""
        abilities = tuple(non_blank(item, "ability") for item in value)
        if len(set(abilities)) != len(abilities):
            raise ValueError("role abilities must be unique")
        return abilities


class StoryThemeSettings(BaseModel):
    """Presentation-only terminology supplied with a game setup."""

    id: str
    name: str
    summary: str
    premise: str
    role_names: dict[str, str]
    role_objectives: dict[str, str]
    faction_names: dict[str, str]
    ability_names: dict[str, str]
    action_names: dict[str, str]
    phase_names: dict[str, str]
    narration: dict[str, tuple[str, ...]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)


class SetupMechanicsSettings(BaseModel):
    """Deterministic mechanics supplied with a custom setup."""

    role_counts: dict[str, RoleCount]
    roles: dict[str, SetupRoleDefinition]
    abilities: dict[str, SetupAbilityDefinition]
    rules: LocalRulesSettings
    composition: RuleCompositionSelection = Field(
        default_factory=lambda: RuleCompositionSelection()
    )

    model_config = ConfigDict(extra="forbid", frozen=True)


class SetupRosterSettings(BaseModel):
    """Characters and fixed seat assignments supplied with a setup."""

    characters: dict[str, CustomCharacterDefinitionRequest] = Field(default_factory=dict)
    assignments: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameSetupDocumentRequest(BaseModel):
    """Complete portable setup document."""

    schema_version: Literal[1] = 1
    mechanics: SetupMechanicsSettings
    theme: StoryThemeSettings
    roster: SetupRosterSettings = Field(default_factory=SetupRosterSettings)

    model_config = ConfigDict(extra="forbid", frozen=True)


class PresetSetupRequest(BaseModel):
    """Select a packaged setup preset."""

    mode: Literal["preset"]
    preset_id: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class CustomSetupRequest(BaseModel):
    """Supply a complete custom setup."""

    mode: Literal["custom"]
    setup: GameSetupDocumentRequest

    model_config = ConfigDict(extra="forbid", frozen=True)


GameSetupSelectionRequest = Annotated[
    PresetSetupRequest | CustomSetupRequest,
    Field(discriminator="mode"),
]


class RuleCompositionSelection(BaseModel):
    """Registered rule policies selected for one game."""

    phases: tuple[str, ...] = ("night", "day_discussion", "voting")
    action_policy: str = "standard"
    resolution_policy: str = "standard"
    phase_policy: str = "required_actions"
    victory_policy: str = "faction_balance"
    visibility_policy: str = "standard"

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator(
        "action_policy",
        "resolution_policy",
        "phase_policy",
        "victory_policy",
        "visibility_policy",
    )
    @classmethod
    def validate_policy_id(cls, value: str, info: ValidationInfo) -> str:
        """Return a normalized policy id."""
        return non_blank(value, str(info.field_name))


SetupMechanicsSettings.model_rebuild()


class CreateGameRequest(BaseModel):
    """Payload for creating one game."""

    seed: int | None = None
    setup: GameSetupSelectionRequest
    manual_player_id: str | None = None
    narration_mode: NarrationMode = DEFAULT_NARRATION_MODE

    model_config = ConfigDict(extra="forbid")

    @field_validator("manual_player_id")
    @classmethod
    def validate_manual_player_id(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Return a stripped optional manual player id."""
        return optional_non_blank(value, str(info.field_name))

    @model_validator(mode="after")
    def validate_manual_player_within_generated_seats(self) -> Self:
        """Ensure the requested manual seat exists in the generated table."""
        if self.setup.mode == "preset":
            return self
        valid_player_ids = generated_player_ids(self.player_count)
        if self.manual_player_id is not None and self.manual_player_id not in valid_player_ids:
            raise ValueError(MESSAGE_MANUAL_PLAYER_ID_MUST_MATCH_PLAYERS)
        unknown_assignments = sorted(set(self.setup.setup.roster.assignments) - valid_player_ids)
        if unknown_assignments:
            raise ValueError(MESSAGE_CHARACTER_ASSIGNMENTS_KEYS_MUST_MATCH_PLAYERS)
        return self

    @property
    def player_count(self) -> int:
        """Return the player count derived from role counts."""
        if self.setup.mode == "preset":
            raise ValueError("player_count is resolved from the selected preset")
        return sum(self.setup.setup.mechanics.role_counts.values())


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
    identity_faction: str
    victory_team: str
    objective: str
    abilities: list[str]
    description: str = ""
    difficulty: int = Field(default=MIN_DIFFICULTY, ge=MIN_DIFFICULTY, le=MAX_DIFFICULTY)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("id", "name", "identity_faction", "victory_team", "objective")
    @classmethod
    def validate_non_blank(cls, value: str, info: ValidationInfo) -> str:
        """Return a stripped non-empty string."""
        return non_blank(value, str(info.field_name))


class RulePolicyOptionView(BaseModel):
    """Public display metadata for one registered rule policy."""

    id: str
    name: str
    description: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class RulePhaseOrderOptionView(BaseModel):
    """Public display metadata for one supported phase order."""

    id: str
    name: str
    description: str
    phases: tuple[str, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)


class RuleCompositionOptionsView(BaseModel):
    """Selectable registered policies and the current default composition."""

    default: RuleCompositionSelection
    phase_orders: list[RulePhaseOrderOptionView]
    action_policies: list[RulePolicyOptionView]
    resolution_policies: list[RulePolicyOptionView]
    phase_policies: list[RulePolicyOptionView]
    victory_policies: list[RulePolicyOptionView]
    visibility_policies: list[RulePolicyOptionView]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_non_empty_policy_options(self) -> Self:
        """Reject a server setup that cannot produce a complete composition."""
        for field_name in (
            "phase_orders",
            "action_policies",
            "resolution_policies",
            "phase_policies",
            "victory_policies",
            "visibility_policies",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must contain at least one option")
        return self


def _default_rule_composition_options() -> RuleCompositionOptionsView:
    selection = RuleCompositionSelection()
    return RuleCompositionOptionsView(
        default=selection,
        phase_orders=[
            RulePhaseOrderOptionView(
                id="standard",
                name="標準のphase順序",
                description="夜、昼の議論、投票の順に進行します。",
                phases=selection.phases,
            )
        ],
        action_policies=[
            RulePolicyOptionView(id="standard", name="標準", description="標準の行動判定")
        ],
        resolution_policies=[
            RulePolicyOptionView(id="standard", name="標準", description="標準の行動解決")
        ],
        phase_policies=[
            RulePolicyOptionView(
                id="required_actions",
                name="必要行動を待つ",
                description="必要な行動が揃ってから進行",
            )
        ],
        victory_policies=[
            RulePolicyOptionView(
                id="faction_balance",
                name="陣営人数",
                description="生存人数から勝敗を判定",
            )
        ],
        visibility_policies=[
            RulePolicyOptionView(id="standard", name="標準", description="標準の公開範囲")
        ],
    )


class GameSetupOptionsResponse(BaseModel):
    """Public setup metadata for client bootstrapping."""

    player_count: dict[str, int]
    roles: list[RoleDefinitionView]
    default_role_counts: dict[RoleId, RoleCount]
    default_rules: LocalRulesSettings
    default_scenario_id: str | None = None
    default_setup_preset_id: str | None = None
    default_narration_mode: NarrationMode = DEFAULT_NARRATION_MODE
    abilities: list[AbilityDefinitionView] = Field(default_factory=list)
    scenarios: list[ScenarioDefinitionView] = Field(default_factory=list)
    setup_presets: list[SetupPresetDefinitionView] = Field(default_factory=list)
    characters: list[CharacterDefinitionView] = Field(default_factory=list)
    rule_composition: RuleCompositionOptionsView = Field(
        default_factory=_default_rule_composition_options
    )

    model_config = ConfigDict(extra="forbid", frozen=True)


class AbilityDefinitionView(BaseModel):
    """Public ability metadata for setup screens."""

    id: str
    name: str
    description: str
    phase: str
    action: str
    validation_policy: str
    resolution_policy: str
    target_policy: str
    effect: str
    max_uses: int | None = None
    start_day: int = Field(default=1, ge=1)
    result_visibility: Literal["private", "public", "none"] = "private"
    resolution_priority: int = Field(default=100, ge=0, le=1000)
    difficulty: int = Field(ge=MIN_DIFFICULTY, le=MAX_DIFFICULTY)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator(
        "id",
        "name",
        "description",
        "phase",
        "action",
        "validation_policy",
        "resolution_policy",
        "target_policy",
        "effect",
    )
    @classmethod
    def validate_non_blank(cls, value: str, info: ValidationInfo) -> str:
        """Return a stripped non-empty string."""
        return non_blank(value, str(info.field_name))


class ScenarioDefinitionView(BaseModel):
    """Public scenario metadata for setup screens."""

    id: str
    name: str
    summary: str
    premise: str
    recommended_setup_preset: str | None = None
    role_names: dict[str, str] = Field(default_factory=dict)
    role_objectives: dict[str, str] = Field(default_factory=dict)
    faction_names: dict[str, str] = Field(default_factory=dict)
    ability_names: dict[str, str] = Field(default_factory=dict)
    action_names: dict[str, str] = Field(default_factory=dict)
    phase_names: dict[str, str] = Field(default_factory=dict)
    narration: dict[str, tuple[str, ...]] = Field(default_factory=dict)

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
    "AbilityDefinitionView",
    "ActionType",
    "AdvanceGameJobResponse",
    "AdvanceGameResponse",
    "AdvanceJobStatus",
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
    "RecoveryAction",
    "RoleCount",
    "RoleDefinitionView",
    "RoleId",
    "RuleCompositionOptionsView",
    "RuleCompositionSelection",
    "RulePhaseOrderOptionView",
    "RulePolicyOptionView",
    "ScenarioDefinitionView",
    "SetupPresetDefinitionView",
    "Winner",
]
