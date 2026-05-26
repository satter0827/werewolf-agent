"""Stateless game use cases that orchestrate domain rules and ports."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from werewolf_agent.contracts import GameError, GamePhaseError
from werewolf_agent.domain.models import (
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
from werewolf_agent.domain.service import advance_phase, observe, start_game, submit_action
from werewolf_agent.usecase.models import (
    CreateGameCommand,
    CreateGamePlayer,
    GameEventsResponse,
    GameResponse,
    GameRunUpdate,
    GameUseCaseSettings,
    NewGameRun,
    RoleId,
    RulesetResponse,
    StepGameResponse,
)
from werewolf_agent.usecase.ports import AgentFactory, GameRunRepository, Logger, RandomFactory
from werewolf_agent.usecase.projections import (
    events_to_persist,
    public_event_from_record,
    public_state_from_run,
    public_state_from_snapshot,
)
from werewolf_agent.usecase.rulesets import default_ruleset


class GameNotFoundError(Exception):
    """Raised when a requested game run is absent from the repository."""


@dataclass(frozen=True)
class GameUseCaseDependencies:
    """Externally supplied dependencies for game use cases."""

    repository: GameRunRepository
    agent_factory: AgentFactory
    rng_factory: RandomFactory
    game_id_factory: Callable[[], UUID]
    logger: Logger
    settings: GameUseCaseSettings


def get_default_ruleset(*, settings: GameUseCaseSettings) -> RulesetResponse:
    """Return public metadata for the default ruleset."""
    return default_ruleset(settings)


def create_game(
    command: CreateGameCommand,
    *,
    dependencies: GameUseCaseDependencies,
) -> GameResponse:
    """Create and persist one deterministic game."""
    game_id = dependencies.game_id_factory()
    _validate_agent_config(command, dependencies.settings)
    players = _player_configs(command, dependencies.settings)
    config = _domain_config(command, game_id=str(game_id), player_count=len(players))
    snapshot, events = start_game(config, players, dependencies.rng_factory(command.seed))
    public_state = public_state_from_snapshot(
        snapshot,
        version=1,
        seed=command.seed,
    )
    run = dependencies.repository.create(
        NewGameRun(
            id=game_id,
            status=public_state.status,
            phase=public_state.phase,
            day=public_state.day,
            seed=command.seed,
            config=config.model_dump(mode="json"),
            public_state=public_state.model_dump(mode="json"),
            private_state=snapshot.model_dump(mode="json"),
            version=1,
        )
    )
    dependencies.repository.append_events(run.id, events_to_persist(events))
    dependencies.logger.debug("Created game run.", extra={"game_id": str(run.id)})
    return GameResponse(game_id=str(run.id), state=public_state_from_run(run))


def get_game(game_id: UUID, *, repository: GameRunRepository) -> GameResponse:
    """Return the current public state for one game run."""
    run = repository.get(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))
    return GameResponse(game_id=str(run.id), state=public_state_from_run(run))


def advance_game(
    game_id: UUID,
    *,
    dependencies: GameUseCaseDependencies,
) -> StepGameResponse:
    """Advance one game run by one business step."""
    run = dependencies.repository.get_for_update(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))
    if run.status == "completed":
        raise GamePhaseError("Finished games cannot be advanced.")

    snapshot = GameSnapshot.model_validate(run.private_state)
    runtime_rng = dependencies.rng_factory(_runtime_seed(run.seed, run.version))
    pending_actions = PendingActions()
    snapshot, pending_actions, action_events = _drive_current_phase(
        snapshot,
        seed=run.seed,
        version=run.version,
        agent_factory=dependencies.agent_factory,
        pending_actions=pending_actions,
    )
    next_snapshot, _next_pending_actions, phase_events = advance_phase(
        snapshot,
        pending_actions,
        runtime_rng,
    )
    next_public_state = public_state_from_snapshot(
        next_snapshot,
        version=run.version + 1,
        seed=run.seed,
        created_at=run.created_at,
    )

    updated_run = dependencies.repository.save(
        GameRunUpdate(
            id=run.id,
            status=next_public_state.status,
            phase=next_public_state.phase,
            day=next_public_state.day,
            public_state=next_public_state.model_dump(mode="json"),
            private_state=next_snapshot.model_dump(mode="json"),
            version=run.version + 1,
        )
    )
    records = dependencies.repository.append_events(
        updated_run.id,
        events_to_persist([*action_events, *phase_events]),
    )
    dependencies.logger.debug(
        "Advanced game run.",
        extra={"game_id": str(updated_run.id), "version": updated_run.version},
    )
    return StepGameResponse(
        game_id=str(updated_run.id),
        status=updated_run.status,
        state=public_state_from_run(updated_run),
        events=[
            public_event_from_record(record) for record in records if record.visibility == "public"
        ],
    )


def list_public_events(
    game_id: UUID,
    *,
    repository: GameRunRepository,
    after: int = 0,
) -> GameEventsResponse:
    """List public events after a sequence number."""
    run = repository.get(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))

    records = repository.list_public_events(run.id, after=after)
    next_after = records[-1].sequence if records else after
    return GameEventsResponse(
        game_id=str(run.id),
        events=[public_event_from_record(record) for record in records],
        next_after=next_after,
    )


def _player_configs(
    command: CreateGameCommand,
    settings: GameUseCaseSettings,
) -> list[Player]:
    if command.players is not None:
        _validate_players(command.players, settings)
        return [Player(id=player.id, name=player.name) for player in command.players]

    player_count = _resolved_player_count(command, settings)
    if player_count < settings.min_players or player_count > settings.max_players:
        raise GameError(
            f"player_count must be between {settings.min_players} and {settings.max_players}."
        )
    return [
        Player(id=f"player-{index}", name=f"Player {index}") for index in range(1, player_count + 1)
    ]


def _resolved_player_count(
    command: CreateGameCommand,
    settings: GameUseCaseSettings,
) -> int:
    if command.player_count is not None:
        return command.player_count
    return settings.default_player_count


def _validate_players(
    players: Sequence[CreateGamePlayer],
    settings: GameUseCaseSettings,
) -> None:
    if len(players) < settings.min_players or len(players) > settings.max_players:
        raise GameError(
            f"player count must be between {settings.min_players} and {settings.max_players}."
        )

    unsupported_agent_types = sorted(
        {
            player.agent_type
            for player in players
            if player.agent_type != settings.supported_agent_type
        }
    )
    if unsupported_agent_types:
        raise GameError("Only dummy agent_type is supported for the MVP API.")

    duplicate_ids = sorted(
        player_id
        for player_id, count in Counter(player.id for player in players).items()
        if count > 1
    )
    if duplicate_ids:
        raise GameError("player id values must be unique.")


def _validate_agent_config(command: CreateGameCommand, settings: GameUseCaseSettings) -> None:
    if command.agent.type != settings.supported_agent_type:
        raise GameError("Only dummy agent type is supported for the MVP API.")


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
    agent_factory: AgentFactory,
    pending_actions: PendingActions,
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
