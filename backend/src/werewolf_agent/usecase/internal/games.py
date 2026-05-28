"""Internal implementations for game use case jobs."""

from __future__ import annotations

import hashlib
import hmac
import random
import secrets
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import cast
from uuid import UUID, uuid4

from werewolf_agent.commons.shared.messages import (
    MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED,
    MESSAGE_GAME_ID_MUST_BE_VALID_UUID,
    MESSAGE_INVALID_CONTROL_TOKEN,
    MESSAGE_PLAYER_ID_VALUES_MUST_BE_UNIQUE,
    MESSAGE_PLAYER_IS_NOT_MANUAL,
    MESSAGE_UNSUPPORTED_HUMAN_PLAYER_COUNT,
    message_player_count_between,
    message_supported_agent_type_only,
    message_supported_player_agent_type_only,
)
from werewolf_agent.contracts import (
    GameError,
    GameNotFoundError,
    GamePhaseError,
    InvalidControlTokenError,
    InvalidGameIdError,
)
from werewolf_agent.domain.game.models import (
    Action,
    ActionType,
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
from werewolf_agent.usecase.internal.agents import AgentFactory, fake_llm_agent_factory
from werewolf_agent.usecase.internal.projections import (
    events_to_create,
    public_event_payload_from_record,
    public_run_summary_payload_from_record,
    public_state_payload_from_run,
    public_state_payload_from_snapshot,
    public_turn_payload_from_record,
)
from werewolf_agent.usecase.jobs.games import (
    AdvanceGameRunCommand,
    AdvanceGameRunResult,
    CreateGamePlayer,
    CreateGameRunCommand,
    GamePhase,
    GameRunCreate,
    GameRunResult,
    GameRunUpdate,
    GameStatus,
    GameUseCaseConfig,
    GameUseCaseDependencies,
    GetGameRunQuery,
    GetPlayerObservationQuery,
    ListGameRunsQuery,
    ListGameRunsResult,
    ListPublicGameEventsQuery,
    ListPublicGameTurnsQuery,
    ListPublicGameTurnsResult,
    PlayerObservationResult,
    PublicGameEventsResult,
    RoleId,
    StoredGameRun,
    SubmitPlayerActionCommand,
    SubmitPlayerActionResult,
)


def create_game_run(
    command: CreateGameRunCommand,
    *,
    dependencies: GameUseCaseDependencies,
) -> GameRunResult:
    """Create and persist one deterministic game."""
    game_id = uuid4()
    _validate_agent_config(command, dependencies.config)
    players = _player_configs(command, dependencies.config)
    control_tokens = _control_tokens_for(command)
    config = _domain_config(command, game_id=str(game_id), player_count=len(players))
    run_config = config.model_dump(mode="json")
    run_config["player_agent_types"] = {
        player.id: command_player.agent_type
        for player, command_player in zip(
            players,
            _requested_player_configs(command, players),
            strict=True,
        )
    }
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
            config=run_config,
            public_state=public_state,
            private_state=snapshot.model_dump(mode="json"),
            pending_actions=PendingActions().model_dump(mode="json"),
            control_token_hashes=_control_token_hashes(control_tokens),
            version=1,
        )
    )
    dependencies.repository.append_events(run.id, events_to_create(events))
    return GameRunResult(
        game_id=str(run.id),
        state=public_state_payload_from_run(run),
        control_tokens=control_tokens or None,
    )


def get_game_run(
    query: GetGameRunQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> GameRunResult:
    """Return the current public state for one game run."""
    game_id = _parse_game_id(query.game_id)
    run = dependencies.repository.get(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))
    return GameRunResult(game_id=str(run.id), state=public_state_payload_from_run(run))


def list_game_runs(
    query: ListGameRunsQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> ListGameRunsResult:
    """Return a page of public game run summaries."""
    records = dependencies.repository.list_run_summaries(
        status=query.status,
        limit=query.limit,
        offset=query.offset,
    )
    next_offset = query.offset + len(records) if len(records) == query.limit else None
    return ListGameRunsResult(
        runs=[public_run_summary_payload_from_record(record) for record in records],
        next_offset=next_offset,
    )


def advance_game_run(
    command: AdvanceGameRunCommand,
    *,
    dependencies: GameUseCaseDependencies,
) -> AdvanceGameRunResult:
    """Advance one game run by one business step."""
    game_id = _parse_game_id(command.game_id)
    run = dependencies.repository.get_for_update(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))
    if run.status == "completed":
        raise GamePhaseError(MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED)

    snapshot = GameSnapshot.model_validate(run.private_state)
    runtime_rng = random.Random(_runtime_seed(run.seed, run.version))
    pending_actions = PendingActions.model_validate(run.pending_actions)
    snapshot, pending_actions, action_events = _drive_current_phase(
        snapshot,
        seed=run.seed,
        version=run.version,
        pending_actions=pending_actions,
        agent_factory=fake_llm_agent_factory(dependencies.fake_llm_config),
        human_player_ids=_human_player_ids(run.config),
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
            pending_actions=_next_pending_actions.model_dump(mode="json"),
            version=run.version + 1,
        )
    )
    records = dependencies.repository.append_events(
        updated_run.id,
        events_to_create([*action_events, *phase_events]),
    )
    return AdvanceGameRunResult(
        game_id=str(updated_run.id),
        status=updated_run.status,
        state=public_state_payload_from_run(updated_run),
        events=[
            public_event_payload_from_record(record)
            for record in records
            if record.visibility == "public"
        ],
    )


def get_player_observation(
    query: GetPlayerObservationQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> PlayerObservationResult:
    """Return one authenticated player's private observation."""
    game_id = _parse_game_id(query.game_id)
    run = dependencies.repository.get(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))
    _authorize_manual_player(run, query.player_id, query.control_token)
    snapshot = GameSnapshot.model_validate(run.private_state)
    observation = observe(snapshot, query.player_id)
    return PlayerObservationResult(
        game_id=str(run.id),
        player_id=query.player_id,
        observation=observation.model_dump(mode="json"),
    )


def submit_player_action(
    command: SubmitPlayerActionCommand,
    *,
    dependencies: GameUseCaseDependencies,
) -> SubmitPlayerActionResult:
    """Submit one authenticated manual player action."""
    game_id = _parse_game_id(command.game_id)
    run = dependencies.repository.get_for_update(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))
    if run.status == "completed":
        raise GamePhaseError(MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED)

    _authorize_manual_player(run, command.player_id, command.control_token)
    snapshot = GameSnapshot.model_validate(run.private_state)
    pending_actions = PendingActions.model_validate(run.pending_actions)
    action = Action(
        type=ActionType(command.type),
        player_id=command.player_id,
        target_id=command.target_id,
        message=command.message,
        reason=command.reason,
    )
    next_snapshot, next_pending_actions, events = submit_action(snapshot, pending_actions, action)
    next_public_state = public_state_payload_from_snapshot(
        next_snapshot,
        version=run.version,
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
            pending_actions=next_pending_actions.model_dump(mode="json"),
            version=run.version,
        )
    )
    records = dependencies.repository.append_events(updated_run.id, events_to_create(events))
    return SubmitPlayerActionResult(
        game_id=str(updated_run.id),
        player_id=command.player_id,
        state=public_state_payload_from_run(updated_run),
        events=[
            public_event_payload_from_record(record)
            for record in records
            if record.visibility == "public"
        ],
    )


def list_public_game_events(
    query: ListPublicGameEventsQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> PublicGameEventsResult:
    """List public events after a sequence number."""
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
    return PublicGameEventsResult(
        game_id=str(run.id),
        events=[public_event_payload_from_record(record) for record in records],
        next_after=next_after,
    )


def list_public_game_turns(
    query: ListPublicGameTurnsQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> ListPublicGameTurnsResult:
    """List public turn records after a sequence number."""
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
    return ListPublicGameTurnsResult(
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
    command: CreateGameRunCommand,
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
    command: CreateGameRunCommand,
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
            if player.agent_type not in {config.supported_agent_type, "human"}
        }
    )
    if unsupported_agent_types:
        raise GameError(message_supported_player_agent_type_only(config.supported_agent_type))
    if sum(1 for player in players if player.agent_type == "human") > 1:
        raise GameError(MESSAGE_UNSUPPORTED_HUMAN_PLAYER_COUNT)

    duplicate_ids = sorted(
        player_id
        for player_id, count in Counter(player.id for player in players).items()
        if count > 1
    )
    if duplicate_ids:
        raise GameError(MESSAGE_PLAYER_ID_VALUES_MUST_BE_UNIQUE)


def _validate_agent_config(command: CreateGameRunCommand, config: GameUseCaseConfig) -> None:
    if command.agent.type != config.supported_agent_type:
        raise GameError(message_supported_agent_type_only(config.supported_agent_type))


def _domain_config(
    command: CreateGameRunCommand,
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


def _requested_player_configs(
    command: CreateGameRunCommand,
    players: Sequence[Player],
) -> list[CreateGamePlayer]:
    if command.players is not None:
        return list(command.players)
    return [
        CreateGamePlayer(id=player.id, name=player.name, agent_type="llm") for player in players
    ]


def _control_tokens_for(command: CreateGameRunCommand) -> dict[str, str]:
    if command.players is None:
        return {}
    return {
        player.id: secrets.token_urlsafe(32)
        for player in command.players
        if player.agent_type == "human"
    }


def _control_token_hashes(control_tokens: Mapping[str, str]) -> dict[str, str]:
    return {player_id: _hash_control_token(token) for player_id, token in control_tokens.items()}


def _hash_control_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _authorize_manual_player(
    run: StoredGameRun,
    player_id: str,
    control_token: str,
) -> None:
    if player_id not in _human_player_ids(run.config):
        raise InvalidControlTokenError(MESSAGE_PLAYER_IS_NOT_MANUAL)
    expected_hash = run.control_token_hashes.get(player_id)
    if expected_hash is None or not hmac.compare_digest(
        expected_hash,
        _hash_control_token(control_token),
    ):
        raise InvalidControlTokenError(MESSAGE_INVALID_CONTROL_TOKEN)


def _human_player_ids(config: Mapping[str, object]) -> set[str]:
    agent_types = config.get("player_agent_types")
    if not isinstance(agent_types, dict):
        return set()
    return {
        str(player_id) for player_id, agent_type in agent_types.items() if agent_type == "human"
    }


def _drive_current_phase(
    snapshot: GameSnapshot,
    *,
    seed: int | None,
    version: int,
    pending_actions: PendingActions,
    agent_factory: AgentFactory,
    human_player_ids: set[str],
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
            if player.id in human_player_ids:
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
