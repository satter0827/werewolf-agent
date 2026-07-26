"""Results returned by application operations."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import ConfigDict, Field

from werewolf_agent.application.constants import (
    DEFAULT_NARRATION_MODE,
    MIN_SEQUENCE,
    MIN_VERSION,
    NarrationMode,
)
from werewolf_agent.application.definitions import (
    LocalRulesDefinition,
)
from werewolf_agent.application.models.base import ApplicationModel
from werewolf_agent.application.types import (
    Faction,
    GamePhase,
    GameStatus,
    RoleCount,
    RoleId,
    Winner,
)

if TYPE_CHECKING:
    pass

EventVisibility = Literal["public", "player_private", "debug"]
ActionTypeId = str


class GameSetupOptionsResult(ApplicationModel):
    """Game setup metadata returned by application operations."""

    player_count: dict[str, int]
    roles: dict[RoleId, dict[str, Any]]
    default_role_counts: dict[RoleId, RoleCount]
    default_rules: LocalRulesDefinition
    default_scenario_id: str | None = None
    default_setup_preset_id: str | None = None
    default_narration_mode: NarrationMode = DEFAULT_NARRATION_MODE
    abilities: dict[str, dict[str, Any]] = Field(default_factory=dict)
    scenarios: dict[str, dict[str, Any]] = Field(default_factory=dict)
    narration_profiles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    setup_presets: dict[str, dict[str, Any]] = Field(default_factory=dict)
    characters: dict[str, dict[str, Any]] = Field(default_factory=dict)
    rule_composition: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)


class SetupValidationResult(ApplicationModel):
    """Normalized summary of one semantically valid complete setup."""

    schema_version: int
    player_count: int
    theme_id: str
    theme_name: str
    role_ids: tuple[str, ...]
    ability_ids: tuple[str, ...]
    setup_checksum: str
    mechanics_checksum: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameResult(ApplicationModel):
    """Current game state returned by application operations."""

    game_id: str
    state: dict[str, Any]

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealPlayer(ApplicationModel):
    """Full player state for the dedicated reveal boundary."""

    id: str
    name: str
    role: RoleId
    identity_faction: Faction
    victory_team: Faction
    objective: str
    alive: bool
    status: str
    eliminated_day: int | None = None
    killed_night: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealAction(ApplicationModel):
    """Pending action for the dedicated reveal boundary."""

    player_id: str
    type: ActionTypeId
    target_id: str | None = None
    message: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealInspection(ApplicationModel):
    """Resolved inspection for the dedicated reveal boundary."""

    seer_id: str
    target_id: str
    target_role: RoleId
    target_faction: Faction

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealNight(ApplicationModel):
    """Resolved night record for the dedicated reveal boundary."""

    day: int
    attacked_player_id: str | None = None
    protected_player_id: str | None = None
    killed_player_id: str | None = None
    inspections: list[GameRevealInspection] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealVote(ApplicationModel):
    """Resolved vote record for the dedicated reveal boundary."""

    day: int
    votes: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    tied_player_ids: list[str] = Field(default_factory=list)
    missing_voter_ids: list[str] = Field(default_factory=list)
    eliminated_player_id: str | None = None
    tie_break_policy: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealResult(ApplicationModel):
    """Full table information for admin observer views."""

    game_id: str
    status: GameStatus
    phase: GamePhase
    day: int
    version: int
    seed: int | None
    scenario_id: str | None = None
    scenario_name: str | None = None
    narration_mode: NarrationMode = DEFAULT_NARRATION_MODE
    theme: dict[str, Any] | None = None
    role_counts: dict[RoleId, RoleCount]
    rules: LocalRulesDefinition
    players: list[GameRevealPlayer]
    alive_player_ids: list[str]
    eliminated_player_ids: list[str]
    winner: Winner | None = None
    pending_votes: list[GameRevealAction] = Field(default_factory=list)
    pending_night_actions: list[GameRevealAction] = Field(default_factory=list)
    votes: list[GameRevealVote] = Field(default_factory=list)
    nights: list[GameRevealNight] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerObservationResult(ApplicationModel):
    """Private observation returned to an authenticated player."""

    game_id: str
    player_id: str
    observation: dict[str, Any]

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerActionResult(ApplicationModel):
    """Result after accepting one manual player action."""

    game_id: str
    player_id: str
    state: dict[str, Any]
    timeline: list[dict[str, Any]]

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceGameResult(ApplicationModel):
    """Result from advancing a game by one application step."""

    game_id: str
    status: GameStatus
    state: dict[str, Any]
    timeline: list[dict[str, Any]]

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameTimelineResult(ApplicationModel):
    """Page of public timeline items."""

    game_id: str
    items: list[dict[str, Any]]
    next_after: int

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameListResult(ApplicationModel):
    """Page of public game summaries."""

    games: list[dict[str, Any]]
    next_offset: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class ReplayVerificationResult(ApplicationModel):
    """Private-payload-free replay integrity result."""

    game_id: str
    valid: bool
    checked_versions: int = Field(ge=0)
    first_mismatch_version: int | None = Field(default=None, ge=MIN_VERSION)
    comparison_target: str | None = None
    expected_checksum: str | None = None
    actual_checksum: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicPlayerState(ApplicationModel):
    """Internal public player state projected from domain state."""

    id: str
    name: str
    alive: bool
    status: str
    eliminated_day: int | None = None
    killed_night: int | None = None
    role: str | None = None
    faction: Faction | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicGameState(ApplicationModel):
    """Internal public game state projected from domain state."""

    game_id: str
    status: GameStatus
    phase: GamePhase
    day: int
    version: int
    seed: int | None
    scenario_id: str | None = None
    scenario_name: str | None = None
    narration_mode: NarrationMode = DEFAULT_NARRATION_MODE
    theme: dict[str, Any] | None = None
    players: list[PublicPlayerState]
    alive_player_ids: list[str]
    eliminated_player_ids: list[str]
    winner: Winner | None = None
    summary: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicGameSummary(ApplicationModel):
    """Public summary of a persisted game."""

    game_id: str
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


class GameTimelineItem(ApplicationModel):
    """Public turn/event record optimized for external timelines."""

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


class GameEventCreate(ApplicationModel):
    """Sanitized event data to persist through an outer repository."""

    visibility: EventVisibility
    phase: GamePhase | None = None
    day: int | None = None
    actor_id: str | None = None
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)
