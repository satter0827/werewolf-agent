"""Stateless game jobs that orchestrate business workflow and domain rules."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from werewolf_agent.commons.shared.messages import (
    MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED,
    MESSAGE_GAME_ID_MUST_BE_VALID_UUID,
    MESSAGE_PLAYER_COUNT_MUST_MATCH_PLAYERS,
    MESSAGE_PLAYER_ID_VALUES_MUST_BE_UNIQUE,
    message_player_count_between,
    message_supported_agent_type_only,
    message_supported_player_agent_type_only,
)
from werewolf_agent.commons.shared.validation import non_blank
from werewolf_agent.contracts import GameError, GamePhaseError
from werewolf_agent.domain.game.models import (
    DomainEvent,
    GameConfig,
    GameSnapshot,
    PendingActions,
    Phase,
    Player,
    PlayerStatus,
    Role,
    TieBreakPolicy,
)
from werewolf_agent.domain.game.service import advance_phase, observe, start_game, submit_action

if TYPE_CHECKING:
    from werewolf_agent.usecase.jobs.ports import AgentFactory, GameRepository

GamePhase = Literal["night", "day_discussion", "voting", "finished"]
GameStatus = Literal["running", "completed"]
EventVisibility = Literal["public", "player_private", "debug"]
RoleId = Literal["villager", "werewolf", "seer", "knight"]
TieBreakPolicyId = Literal["no_elimination", "random_elimination"]
Winner = Literal["villagers", "werewolves"]
RoleCount = Annotated[int, Field(ge=0)]


@dataclass(frozen=True)
class GameUseCaseConfig:
    """Business settings used by stateless game jobs."""

    min_players: int = 5
    max_players: int = 8
    default_player_count: int = 6
    supported_agent_type: str = "llm"
    default_ruleset_id: str = "default"


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


class CreateGameCommand(_UseCaseModel):
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


class GetGameQuery(_UseCaseModel):
    """Query for loading one game."""

    game_id: str | UUID

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceGameCommand(_UseCaseModel):
    """Command for advancing one game by one business step."""

    game_id: str | UUID

    model_config = ConfigDict(extra="forbid", frozen=True)


class ListGamesQuery(_UseCaseModel):
    """Query for listing public game runs."""

    status: GameStatus | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class ListPublicEventsQuery(_UseCaseModel):
    """Query for listing public events after a sequence cursor."""

    game_id: str | UUID
    after: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=500)

    model_config = ConfigDict(extra="forbid", frozen=True)


class ListGameTurnsQuery(_UseCaseModel):
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


class GameResult(_UseCaseModel):
    """Current game state returned by use cases."""

    game_id: str
    state: dict[str, Any]

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceGameResult(_UseCaseModel):
    """Result from advancing a game by one use case step."""

    game_id: str
    status: GameStatus
    state: dict[str, Any]
    events: list[dict[str, Any]]

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicEventsResult(_UseCaseModel):
    """Public event stream returned by use cases."""

    game_id: str
    events: list[dict[str, Any]]
    next_after: int

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRunsResult(_UseCaseModel):
    """Page of public game run summaries."""

    runs: list[dict[str, Any]]
    next_offset: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameTurnsResult(_UseCaseModel):
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


def _default_agent_factory() -> AgentFactory:
    from werewolf_agent.usecase.jobs._agents import FakeLlmAgentFactory

    return FakeLlmAgentFactory()


class GameNotFoundError(Exception):
    """Raised when a requested game run is absent from the repository."""


class InvalidGameIdError(Exception):
    """Raised when a game id cannot be parsed as a UUID."""


@dataclass(frozen=True)
class GameUseCaseDependencies:
    """Externally supplied dependencies for stateless game jobs."""

    repository: GameRepository
    config: GameUseCaseConfig = field(default_factory=GameUseCaseConfig)
    agent_factory: AgentFactory = field(default_factory=_default_agent_factory)


def get_default_ruleset(*, config: GameUseCaseConfig) -> RulesetResult:
    """Return business metadata for the default ruleset."""
    from werewolf_agent.usecase.jobs._rulesets import default_ruleset

    return default_ruleset(config)


def create_game(
    command: CreateGameCommand,
    *,
    dependencies: GameUseCaseDependencies,
) -> GameResult:
    """Create and persist one deterministic game."""
    from werewolf_agent.usecase.jobs._projections import (
        events_to_create,
        public_state_payload_from_run,
        public_state_payload_from_snapshot,
    )

    game_id = uuid4()
    _validate_agent_config(command, dependencies.config)
    players = _player_configs(command, dependencies.config)
    config = _domain_config(command, game_id=str(game_id), player_count=len(players))
    snapshot, events = start_game(config, players, random.Random(command.seed))
    public_state = public_state_payload_from_snapshot(
        snapshot,
        version=1,
        seed=command.seed,
    )
    run = dependencies.repository.create(
        GameRunCreate(
            id=game_id,
            status=cast(GameStatus, public_state["status"]),
            phase=cast(GamePhase, public_state["phase"]),
            day=cast(int, public_state["day"]),
            seed=command.seed,
            config=config.model_dump(mode="json"),
            public_state=public_state,
            private_state=snapshot.model_dump(mode="json"),
            version=1,
        )
    )
    dependencies.repository.append_events(run.id, events_to_create(events))
    return GameResult(game_id=str(run.id), state=public_state_payload_from_run(run))


def get_game(
    query: GetGameQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> GameResult:
    """Return the current public state for one game run."""
    from werewolf_agent.usecase.jobs._projections import public_state_payload_from_run

    game_id = _parse_game_id(query.game_id)
    run = dependencies.repository.get(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))
    return GameResult(game_id=str(run.id), state=public_state_payload_from_run(run))


def list_games(
    query: ListGamesQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> GameRunsResult:
    """Return a page of public game run summaries."""
    from werewolf_agent.usecase.jobs._projections import public_run_summary_payload_from_record

    records = dependencies.repository.list_run_summaries(
        status=query.status,
        limit=query.limit,
        offset=query.offset,
    )
    next_offset = query.offset + len(records) if len(records) == query.limit else None
    return GameRunsResult(
        runs=[public_run_summary_payload_from_record(record) for record in records],
        next_offset=next_offset,
    )


def advance_game(
    command: AdvanceGameCommand,
    *,
    dependencies: GameUseCaseDependencies,
) -> AdvanceGameResult:
    """Advance one game run by one business step."""
    from werewolf_agent.usecase.jobs._projections import (
        events_to_create,
        public_event_payload_from_record,
        public_state_payload_from_run,
        public_state_payload_from_snapshot,
    )

    game_id = _parse_game_id(command.game_id)
    run = dependencies.repository.get_for_update(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))
    if run.status == "completed":
        raise GamePhaseError(MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED)

    snapshot = GameSnapshot.model_validate(run.private_state)
    runtime_rng = random.Random(_runtime_seed(run.seed, run.version))
    pending_actions = PendingActions()
    snapshot, pending_actions, action_events = _drive_current_phase(
        snapshot,
        seed=run.seed,
        version=run.version,
        pending_actions=pending_actions,
        agent_factory=dependencies.agent_factory,
    )
    next_snapshot, _next_pending_actions, phase_events = advance_phase(
        snapshot,
        pending_actions,
        runtime_rng,
    )
    next_public_state = public_state_payload_from_snapshot(
        next_snapshot,
        version=run.version + 1,
        seed=run.seed,
        created_at=run.created_at,
    )

    updated_run = dependencies.repository.save(
        GameRunUpdate(
            id=run.id,
            status=cast(GameStatus, next_public_state["status"]),
            phase=cast(GamePhase, next_public_state["phase"]),
            day=cast(int, next_public_state["day"]),
            public_state=next_public_state,
            private_state=next_snapshot.model_dump(mode="json"),
            version=run.version + 1,
        )
    )
    records = dependencies.repository.append_events(
        updated_run.id,
        events_to_create([*action_events, *phase_events]),
    )
    return AdvanceGameResult(
        game_id=str(updated_run.id),
        status=updated_run.status,
        state=public_state_payload_from_run(updated_run),
        events=[
            public_event_payload_from_record(record)
            for record in records
            if record.visibility == "public"
        ],
    )


def list_public_events(
    query: ListPublicEventsQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> PublicEventsResult:
    """List public events after a sequence number."""
    from werewolf_agent.usecase.jobs._projections import public_event_payload_from_record

    game_id = _parse_game_id(query.game_id)
    run = dependencies.repository.get(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))

    records = dependencies.repository.list_public_events(
        run.id,
        after=query.after,
        limit=query.limit,
    )
    next_after = records[-1].sequence if records else query.after
    return PublicEventsResult(
        game_id=str(run.id),
        events=[public_event_payload_from_record(record) for record in records],
        next_after=next_after,
    )


def list_game_turns(
    query: ListGameTurnsQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> GameTurnsResult:
    """List public turn records after a sequence number."""
    from werewolf_agent.usecase.jobs._projections import public_turn_payload_from_record

    game_id = _parse_game_id(query.game_id)
    run = dependencies.repository.get(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))

    records = dependencies.repository.list_public_turns(
        run.id,
        after=query.after,
        limit=query.limit,
    )
    next_after = records[-1].sequence if records else query.after
    return GameTurnsResult(
        game_id=str(run.id),
        turns=[public_turn_payload_from_record(record) for record in records],
        next_after=next_after,
    )


def _parse_game_id(value: str | UUID) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(value)
    except ValueError as exc:
        raise InvalidGameIdError(MESSAGE_GAME_ID_MUST_BE_VALID_UUID) from exc


def _player_configs(
    command: CreateGameCommand,
    config: GameUseCaseConfig,
) -> list[Player]:
    if command.players is not None:
        _validate_players(command.players, config)
        return [Player(id=player.id, name=player.name) for player in command.players]

    player_count = _resolved_player_count(command, config)
    if player_count < config.min_players or player_count > config.max_players:
        raise GameError(message_player_count_between(config.min_players, config.max_players))
    return [
        Player(id=f"player-{index}", name=f"Player {index}") for index in range(1, player_count + 1)
    ]


def _resolved_player_count(
    command: CreateGameCommand,
    config: GameUseCaseConfig,
) -> int:
    if command.player_count is not None:
        return command.player_count
    return config.default_player_count


def _validate_players(
    players: Sequence[CreateGamePlayer],
    config: GameUseCaseConfig,
) -> None:
    if len(players) < config.min_players or len(players) > config.max_players:
        raise GameError(message_player_count_between(config.min_players, config.max_players))

    unsupported_agent_types = sorted(
        {
            player.agent_type
            for player in players
            if player.agent_type != config.supported_agent_type
        }
    )
    if unsupported_agent_types:
        raise GameError(message_supported_player_agent_type_only(config.supported_agent_type))

    duplicate_ids = sorted(
        player_id
        for player_id, count in Counter(player.id for player in players).items()
        if count > 1
    )
    if duplicate_ids:
        raise GameError(MESSAGE_PLAYER_ID_VALUES_MUST_BE_UNIQUE)


def _validate_agent_config(command: CreateGameCommand, config: GameUseCaseConfig) -> None:
    if command.agent.type != config.supported_agent_type:
        raise GameError(message_supported_agent_type_only(config.supported_agent_type))


def _domain_config(
    command: CreateGameCommand,
    *,
    game_id: str,
    player_count: int,
) -> GameConfig:
    rule_config = command.rule_config
    role_counts = _role_counts(player_count, rule_config.role_counts)
    return GameConfig(
        game_id=game_id,
        player_count=player_count,
        role_counts=role_counts,
        seed=command.seed,
        day_speech_turns=rule_config.day_speech_turns,
        tie_break_policy=TieBreakPolicy(rule_config.tie_break_policy),
        allow_self_vote=rule_config.allow_self_vote,
    )


def _drive_current_phase(
    snapshot: GameSnapshot,
    *,
    seed: int | None,
    version: int,
    pending_actions: PendingActions,
    agent_factory: AgentFactory,
) -> tuple[GameSnapshot, PendingActions, list[DomainEvent]]:
    current_snapshot = snapshot
    current_pending_actions = pending_actions
    events: list[DomainEvent] = []
    turn_count = snapshot.config.day_speech_turns if snapshot.phase is Phase.DAY_DISCUSSION else 1
    for turn in range(turn_count):
        turn_snapshot = current_snapshot
        for index, player in enumerate(turn_snapshot.players.values()):
            if player.status is not PlayerStatus.ALIVE:
                continue
            agent = agent_factory.create(
                player.id,
                seed=_agent_seed(seed, version, index, turn),
            )
            action = agent.act(observe(current_snapshot, player.id))
            current_snapshot, current_pending_actions, action_events = submit_action(
                current_snapshot,
                current_pending_actions,
                action,
            )
            events.extend(action_events)
    return current_snapshot, current_pending_actions, events


def _role_counts(
    player_count: int,
    requested_counts: Mapping[RoleId, int] | None,
) -> dict[Role, int]:
    if requested_counts is not None:
        return {Role(role): count for role, count in requested_counts.items()}
    return {
        Role.WEREWOLF: 1,
        Role.SEER: 1,
        Role.KNIGHT: 1,
        Role.VILLAGER: player_count - 3,
    }


def _runtime_seed(seed: int | None, version: int) -> int:
    return (seed or 0) + version * 1009


def _agent_seed(seed: int | None, version: int, index: int, turn: int = 0) -> int:
    return (seed or 0) + version * 1009 + index * 131 + turn * 1709
