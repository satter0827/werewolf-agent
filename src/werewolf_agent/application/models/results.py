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
from werewolf_agent.application.models.base import ApplicationModel
from werewolf_agent.application.types import (
    Faction,
    GamePhase,
    GameStatus,
    RoleCount,
    RoleId,
    Winner,
)
from werewolf_agent.setup import (
    DiscussionDefinition,
    LifecycleDefinition,
    NightDefinition,
    VotingDefinition,
)

if TYPE_CHECKING:
    pass

EventVisibility = Literal["public", "player_private", "debug"]
ActionTypeId = str


class GameSetupOptionsResult(ApplicationModel):
    """Editor用metadataと同梱templateの概要を表す."""

    player_count: dict[str, int]
    recommended_template_id: str
    template_order: tuple[str, ...]
    templates: dict[str, dict[str, str]]
    ability_kinds: tuple[str, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)


class SetupValidationResult(ApplicationModel):
    """意味検証を通過した完全setupの正規化概要を表す."""

    schema_version: str
    player_count: int
    theme_id: str
    theme_name: str
    role_ids: tuple[str, ...]
    ability_ids: tuple[str, ...]
    setup_checksum: str
    mechanics_checksum: str
    warnings: tuple[str, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerPreviewResult(ApplicationModel):
    """公開情報だけを含む生成roster previewを表す."""

    seed: int
    players: tuple[dict[str, object], ...]
    roster_checksum: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameResult(ApplicationModel):
    """Application operationが返す現在のゲーム状態を表す."""

    game_id: str
    state: dict[str, Any]

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealPlayer(ApplicationModel):
    """専用reveal境界が返す完全なplayer状態を表す."""

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
    """専用reveal境界が返す未解決actionを表す."""

    player_id: str
    type: ActionTypeId
    ability_id: str | None = None
    target_id: str | None = None
    utterance: str | None = None
    reason: str | None = None
    topic_id: str | None = None
    position: str | None = None
    relation: str | None = None
    evidence_id: str | None = None
    response_to_id: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealInspection(ApplicationModel):
    """専用reveal境界が返す解決済みinspectionを表す."""

    player_id: str
    ability_id: str
    target_id: str
    target_role: RoleId
    target_faction: Faction

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealNight(ApplicationModel):
    """専用reveal境界が返す解決済みnight記録を表す."""

    day: int
    attacked_player_id: str | None = None
    protected_player_id: str | None = None
    killed_player_id: str | None = None
    inspections: list[GameRevealInspection] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealVote(ApplicationModel):
    """専用reveal境界が返す解決済みvote記録を表す."""

    day: int
    votes: dict[str, str] = Field(default_factory=dict)
    reasons: dict[str, str] = Field(default_factory=dict)
    evidence_ids: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    tied_player_ids: list[str] = Field(default_factory=list)
    missing_voter_ids: list[str] = Field(default_factory=list)
    eliminated_player_id: str | None = None
    tie_break_policy: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealResult(ApplicationModel):
    """管理者observer viewへ返す完全なtable情報を表す."""

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
    discussion: DiscussionDefinition
    voting: VotingDefinition
    night: NightDefinition
    lifecycle: LifecycleDefinition
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


class PlayerObservationResult(ApplicationModel):
    """認証済みplayerへ返すprivate observationを表す."""

    game_id: str
    player_id: str
    observation: dict[str, Any]

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerActionResult(ApplicationModel):
    """Manual playerのactionを受理した結果を表す."""

    game_id: str
    player_id: str
    state: dict[str, Any]
    timeline: list[dict[str, Any]]

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceGameResult(ApplicationModel):
    """ゲームをapplicationの一step進めた結果を表す."""

    game_id: str
    status: GameStatus
    state: dict[str, Any]
    timeline: list[dict[str, Any]]

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameTimelineResult(ApplicationModel):
    """公開timeline itemの一pageを表す."""

    game_id: str
    items: list[dict[str, Any]]
    next_after: int

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameListResult(ApplicationModel):
    """公開ゲーム概要の一pageを表す."""

    games: list[dict[str, Any]]
    next_offset: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class ReplayVerificationResult(ApplicationModel):
    """Private payloadを含まないreplay整合性結果を表す."""

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
    """外側のrepositoryへ保存する安全なevent dataを表す."""

    visibility: EventVisibility
    phase: GamePhase | None = None
    day: int | None = None
    actor_id: str | None = None
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)
