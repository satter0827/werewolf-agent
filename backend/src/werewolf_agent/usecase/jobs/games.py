"""Public game use case DTOs and a small stateless facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from werewolf_agent.commons.shared.messages import MESSAGE_PLAYER_COUNT_MUST_MATCH_PLAYERS
from werewolf_agent.commons.shared.validation import non_blank
from werewolf_agent.usecase.jobs.telemetry import NullTelemetrySink, TelemetrySink

if TYPE_CHECKING:
    from werewolf_agent.usecase.jobs.ports import GameRepository

GamePhase = Literal["night", "day_discussion", "voting", "finished"]
GameStatus = Literal["running", "completed"]
EventVisibility = Literal["public", "player_private", "debug"]
ActionTypeId = Literal["speech", "vote", "werewolf_attack", "seer_inspect", "knight_guard", "pass"]
RoleId = Literal["villager", "werewolf", "seer", "knight"]
TieBreakPolicyId = Literal["no_elimination", "random_elimination"]
Winner = Literal["villagers", "werewolves"]
AdvanceUntilInputStopReason = Literal["manual_input_required", "completed", "hit_limit"]
RoleCount = Annotated[int, Field(ge=0)]


@dataclass(frozen=True)
class LlmProviderConfig:
    """Use case settings for automated LangChain-backed players."""

    provider: str = "fake"
    model: str = "fake-list-llm"
    prompt_file: Path | None = None
    fake_responses_file: Path | None = None

    def __post_init__(self) -> None:
        """Validate provider settings without importing interface settings."""
        non_blank(self.provider, "llm provider")
        non_blank(self.model, "llm model")
        if self.provider != "fake":
            raise ValueError("llm provider must be one of: fake")


@dataclass(frozen=True)
class GameUseCaseConfig:
    """Business settings used by stateless game jobs."""

    min_players: int = 5
    max_players: int = 8
    default_player_count: int = 6
    supported_agent_type: str = "llm"
    default_ruleset_id: str = "default"
    advance_until_input_max_steps: int = 64


@dataclass(frozen=True)
class GameUseCaseDependencies:
    """Externally supplied dependencies for game use cases."""

    repository: GameRepository
    config: GameUseCaseConfig = field(default_factory=GameUseCaseConfig)
    llm_provider_config: LlmProviderConfig = field(default_factory=LlmProviderConfig)
    telemetry: TelemetrySink = field(default_factory=NullTelemetrySink)


class _UseCaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateGamePlayer(_UseCaseModel):
    """One player requested for a new game."""

    id: str
    name: str
    agent_type: str = "llm"

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("id", "name", "agent_type")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        """Return a stripped non-empty string."""
        return non_blank(value, "value")


class CreateGameAgentConfig(_UseCaseModel):
    """Agent selection for automated game runs."""

    type: str = "llm"

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
    allow_action_revisions: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)


class CreateGameRunCommand(_UseCaseModel):
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


class GetGameRunQuery(_UseCaseModel):
    """Query for loading one game."""

    game_id: str | UUID

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceGameRunCommand(_UseCaseModel):
    """Command for advancing one game by one business step."""

    game_id: str | UUID

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceUntilInputCommand(_UseCaseModel):
    """Command for advancing a game until manual input, completion, or limit."""

    game_id: str | UUID
    max_steps: int = Field(default=64, ge=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class GetPlayerObservationQuery(_UseCaseModel):
    """Query for one player's private observation."""

    game_id: str | UUID
    player_id: str
    control_token: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerActionCommand(_UseCaseModel):
    """Command for submitting one manual player action."""

    game_id: str | UUID
    player_id: str
    control_token: str
    type: ActionTypeId
    target_id: str | None = None
    message: str | None = None
    reason: str = ""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ListGameRunsQuery(_UseCaseModel):
    """Query for listing public game runs."""

    status: GameStatus | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class GetGameTimelineQuery(_UseCaseModel):
    """Query for listing public timeline items after a sequence cursor."""

    game_id: str | UUID
    after: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=500)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RulesetResult(_UseCaseModel):
    """Ruleset business metadata returned by use cases."""

    id: str
    player_count: dict[str, int]
    roles: list[RoleId]
    phases: list[GamePhase]
    agent_types: list[str]

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRunResult(_UseCaseModel):
    """Current game state returned by use cases."""

    game_id: str
    state: dict[str, Any]
    control_tokens: dict[str, str] | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerObservationResult(_UseCaseModel):
    """Private observation returned to an authenticated player."""

    game_id: str
    player_id: str
    observation: dict[str, Any]

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerActionResult(_UseCaseModel):
    """Result after accepting one manual player action."""

    game_id: str
    player_id: str
    state: dict[str, Any]
    timeline: list[dict[str, Any]]

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceGameRunResult(_UseCaseModel):
    """Result from advancing a game by one use case step."""

    game_id: str
    status: GameStatus
    state: dict[str, Any]
    timeline: list[dict[str, Any]]

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceUntilInputResult(_UseCaseModel):
    """Result from advancing until a manual player needs to act."""

    game_id: str
    status: GameStatus
    state: dict[str, Any]
    timeline: list[dict[str, Any]]
    stop_reason: AdvanceUntilInputStopReason
    steps: int

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameTimelineResult(_UseCaseModel):
    """Page of public timeline items."""

    game_id: str
    items: list[dict[str, Any]]
    next_after: int

    model_config = ConfigDict(extra="forbid", frozen=True)


class ListGameRunsResult(_UseCaseModel):
    """Page of public game run summaries."""

    runs: list[dict[str, Any]]
    next_offset: int | None = None

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


class PublicGameRunSummary(_UseCaseModel):
    """Public summary of a persisted game run."""

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


class GameTimelineItem(_UseCaseModel):
    """Public turn/event record optimized for external timelines."""

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


class GameEventCreate(_UseCaseModel):
    """Sanitized event data to persist through an outer repository."""

    visibility: EventVisibility
    phase: GamePhase | None = None
    day: int | None = None
    actor_id: str | None = None
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)


class StoredGameTurn(_UseCaseModel):
    """Turn read-model record loaded from an outer persistence adapter."""

    sequence: int
    event_sequence: int
    version: int
    phase: GamePhase | None = None
    day: int | None = None
    actor_id: str | None = None
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


class StoredGameRunSummary(_UseCaseModel):
    """Run summary read model loaded from an outer persistence adapter."""

    game_id: UUID
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
    pending_actions: dict[str, Any] = Field(default_factory=dict)
    control_token_hashes: dict[str, str] = Field(default_factory=dict)
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
    pending_actions: dict[str, Any] = Field(default_factory=dict)
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
    pending_actions: dict[str, Any] = Field(default_factory=dict)
    control_token_hashes: dict[str, str] = Field(default_factory=dict)
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


class GameUseCases:
    """Small facade over internal game workflows with injected dependencies."""

    def __init__(self, dependencies: GameUseCaseDependencies) -> None:
        """Store dependencies used by all game use case calls."""
        self._dependencies = dependencies

    def get_default_ruleset(self) -> RulesetResult:
        """Return business metadata for the default ruleset."""
        from werewolf_agent.usecase.internal.rulesets import default_ruleset

        return default_ruleset(self._dependencies.config)

    def create_game_run(self, command: CreateGameRunCommand) -> GameRunResult:
        """Create and persist one deterministic game."""
        from werewolf_agent.usecase.internal.games import create_game_run

        return create_game_run(command, dependencies=self._dependencies)

    def get_game_run(self, query: GetGameRunQuery) -> GameRunResult:
        """Return the current public state for one game run."""
        from werewolf_agent.usecase.internal.games import get_game_run

        return get_game_run(query, dependencies=self._dependencies)

    def list_game_runs(self, query: ListGameRunsQuery) -> ListGameRunsResult:
        """Return a page of public game run summaries."""
        from werewolf_agent.usecase.internal.games import list_game_runs

        return list_game_runs(query, dependencies=self._dependencies)

    def advance_game_run(self, command: AdvanceGameRunCommand) -> AdvanceGameRunResult:
        """Advance one game run by one business step."""
        from werewolf_agent.usecase.internal.games import advance_game_run

        return advance_game_run(command, dependencies=self._dependencies)

    def advance_until_input(self, command: AdvanceUntilInputCommand) -> AdvanceUntilInputResult:
        """Advance a game until a manual player needs input or the game stops."""
        from werewolf_agent.usecase.internal.games import advance_until_input

        return advance_until_input(command, dependencies=self._dependencies)

    def get_player_observation(
        self,
        query: GetPlayerObservationQuery,
    ) -> PlayerObservationResult:
        """Return one authenticated player's private observation."""
        from werewolf_agent.usecase.internal.games import get_player_observation

        return get_player_observation(query, dependencies=self._dependencies)

    def submit_player_action(self, command: PlayerActionCommand) -> PlayerActionResult:
        """Submit one authenticated manual player action."""
        from werewolf_agent.usecase.internal.games import submit_player_action

        return submit_player_action(command, dependencies=self._dependencies)

    def get_game_timeline(self, query: GetGameTimelineQuery) -> GameTimelineResult:
        """Return public timeline items after a sequence number."""
        from werewolf_agent.usecase.internal.games import get_game_timeline

        return get_game_timeline(query, dependencies=self._dependencies)
