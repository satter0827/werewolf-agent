"""Public game use case job DTOs and stateless facade functions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from werewolf_agent.commons.shared.messages import MESSAGE_PLAYER_COUNT_MUST_MATCH_PLAYERS
from werewolf_agent.commons.shared.validation import non_blank

if TYPE_CHECKING:
    from werewolf_agent.usecase.jobs.ports import GameRepository

FakeLlmStrategy = Literal["seeded", "random"]
GamePhase = Literal["night", "day_discussion", "voting", "finished"]
GameStatus = Literal["running", "completed"]
EventVisibility = Literal["public", "player_private", "debug"]
ActionTypeId = Literal["speech", "vote", "werewolf_attack", "seer_inspect", "knight_guard", "pass"]
RoleId = Literal["villager", "werewolf", "seer", "knight"]
TieBreakPolicyId = Literal["no_elimination", "random_elimination"]
Winner = Literal["villagers", "werewolves"]
RoleCount = Annotated[int, Field(ge=0)]


@dataclass(frozen=True)
class FakeLlmConfig:
    """Use case settings for the FakeLLM automated player."""

    strategy: FakeLlmStrategy = "seeded"
    randomness: float = 0.7
    persona_profiles: tuple[str, ...] = ("cautious", "assertive", "analytical")
    speech_intents: tuple[str, ...] = ("question", "compare", "pressure")
    speech_templates: tuple[str, ...] = (
        "[{persona}] I want to {intent} {target_name}.",
        "[{persona}] {target_name}'s public history looks worth checking.",
        "[{persona}] I will compare today's claims before voting.",
    )
    reason_templates: tuple[str, ...] = (
        "fake_llm {persona} {action} from public signals",
        "fake_llm {persona} {action} with {intent} intent",
    )

    def __post_init__(self) -> None:
        """Validate FakeLLM settings without importing domain models."""
        if self.strategy not in {"seeded", "random"}:
            raise ValueError("fake_llm strategy must be one of: random, seeded")
        if self.randomness < 0 or self.randomness > 1:
            raise ValueError("fake_llm randomness must be between 0 and 1")
        _validate_template_values("persona_profiles", self.persona_profiles)
        _validate_template_values("speech_intents", self.speech_intents)
        _validate_template_values("speech_templates", self.speech_templates)
        _validate_template_values("reason_templates", self.reason_templates)


@dataclass(frozen=True)
class GameUseCaseConfig:
    """Business settings used by stateless game jobs."""

    min_players: int = 5
    max_players: int = 8
    default_player_count: int = 6
    supported_agent_type: str = "llm"
    default_ruleset_id: str = "default"


@dataclass(frozen=True)
class GameUseCaseDependencies:
    """Externally supplied dependencies for stateless game jobs."""

    repository: GameRepository
    config: GameUseCaseConfig = field(default_factory=GameUseCaseConfig)
    fake_llm_config: FakeLlmConfig = field(default_factory=FakeLlmConfig)


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


class GetPlayerObservationQuery(_UseCaseModel):
    """Query for one player's private observation."""

    game_id: str | UUID
    player_id: str
    control_token: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class SubmitPlayerActionCommand(_UseCaseModel):
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


class ListPublicGameEventsQuery(_UseCaseModel):
    """Query for listing public events after a sequence cursor."""

    game_id: str | UUID
    after: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=500)

    model_config = ConfigDict(extra="forbid", frozen=True)


class ListPublicGameTurnsQuery(_UseCaseModel):
    """Query for listing public turn records after a sequence cursor."""

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


class SubmitPlayerActionResult(_UseCaseModel):
    """Result after accepting one manual player action."""

    game_id: str
    player_id: str
    state: dict[str, Any]
    events: list[dict[str, Any]]

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceGameRunResult(_UseCaseModel):
    """Result from advancing a game by one use case step."""

    game_id: str
    status: GameStatus
    state: dict[str, Any]
    events: list[dict[str, Any]]

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicGameEventsResult(_UseCaseModel):
    """Public event stream returned by use cases."""

    game_id: str
    events: list[dict[str, Any]]
    next_after: int

    model_config = ConfigDict(extra="forbid", frozen=True)


class ListGameRunsResult(_UseCaseModel):
    """Page of public game run summaries."""

    runs: list[dict[str, Any]]
    next_offset: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class ListPublicGameTurnsResult(_UseCaseModel):
    """Page of public turn history."""

    game_id: str
    turns: list[dict[str, Any]]
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


class PublicGameTurn(_UseCaseModel):
    """Public turn/event record optimized for UI timelines."""

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


def get_default_ruleset(*, config: GameUseCaseConfig) -> RulesetResult:
    """Return business metadata for the default ruleset."""
    from werewolf_agent.usecase.internal.rulesets import default_ruleset

    return default_ruleset(config)


def create_game_run(
    command: CreateGameRunCommand,
    *,
    dependencies: GameUseCaseDependencies,
) -> GameRunResult:
    """Create and persist one deterministic game."""
    from werewolf_agent.usecase.internal.games import create_game_run as _create_game_run

    return _create_game_run(command, dependencies=dependencies)


def get_game_run(
    query: GetGameRunQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> GameRunResult:
    """Return the current public state for one game run."""
    from werewolf_agent.usecase.internal.games import get_game_run as _get_game_run

    return _get_game_run(query, dependencies=dependencies)


def list_game_runs(
    query: ListGameRunsQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> ListGameRunsResult:
    """Return a page of public game run summaries."""
    from werewolf_agent.usecase.internal.games import list_game_runs as _list_game_runs

    return _list_game_runs(query, dependencies=dependencies)


def advance_game_run(
    command: AdvanceGameRunCommand,
    *,
    dependencies: GameUseCaseDependencies,
) -> AdvanceGameRunResult:
    """Advance one game run by one business step."""
    from werewolf_agent.usecase.internal.games import advance_game_run as _advance_game_run

    return _advance_game_run(command, dependencies=dependencies)


def get_player_observation(
    query: GetPlayerObservationQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> PlayerObservationResult:
    """Return one authenticated player's private observation."""
    from werewolf_agent.usecase.internal.games import (
        get_player_observation as _get_player_observation,
    )

    return _get_player_observation(query, dependencies=dependencies)


def submit_player_action(
    command: SubmitPlayerActionCommand,
    *,
    dependencies: GameUseCaseDependencies,
) -> SubmitPlayerActionResult:
    """Submit one authenticated manual player action."""
    from werewolf_agent.usecase.internal.games import (
        submit_player_action as _submit_player_action,
    )

    return _submit_player_action(command, dependencies=dependencies)


def list_public_game_events(
    query: ListPublicGameEventsQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> PublicGameEventsResult:
    """List public events after a sequence number."""
    from werewolf_agent.usecase.internal.games import (
        list_public_game_events as _list_public_game_events,
    )

    return _list_public_game_events(query, dependencies=dependencies)


def list_public_game_turns(
    query: ListPublicGameTurnsQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> ListPublicGameTurnsResult:
    """List public turn records after a sequence number."""
    from werewolf_agent.usecase.internal.games import (
        list_public_game_turns as _list_public_game_turns,
    )

    return _list_public_game_turns(query, dependencies=dependencies)


def _validate_template_values(field_name: str, values: Sequence[str]) -> None:
    if not values:
        raise ValueError(f"fake_llm {field_name} must include at least one value")
    for value in values:
        non_blank(value, f"fake_llm {field_name}")
