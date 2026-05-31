"""Internal implementations for game use case jobs."""

from __future__ import annotations

import hashlib
import hmac
import random
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID, uuid4

from werewolf_agent.commons.shared.messages import (
    MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED,
    MESSAGE_GAME_ID_MUST_BE_VALID_UUID,
    MESSAGE_INVALID_CONTROL_TOKEN,
    MESSAGE_MANUAL_INPUT_REQUIRED,
    MESSAGE_PLAYER_IS_NOT_MANUAL,
    message_player_count_between,
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
    LocalRules,
    PendingActions,
    Player,
    PlayerStatus,
    RoleCatalog,
)
from werewolf_agent.domain.game.service import advance_phase, observe, start_game, submit_action
from werewolf_agent.usecase.internal.agents import AgentFactory, langchain_agent_factory
from werewolf_agent.usecase.internal.definitions import local_rules_to_domain, to_role_catalog
from werewolf_agent.usecase.internal.players import (
    display_name_for,
    profile_ids_by_player,
    select_players,
)
from werewolf_agent.usecase.internal.projections import (
    events_to_create,
    public_run_summary_payload_from_record,
    public_state_payload_from_run,
    public_state_payload_from_snapshot,
    public_turn_payload_from_record,
    winner_from_snapshot,
)
from werewolf_agent.usecase.jobs.games import (
    AdvanceGameRunCommand,
    AdvanceGameRunResult,
    AdvanceUntilInputCommand,
    AdvanceUntilInputResult,
    CreateGameCommand,
    GamePhase,
    GameRevealAction,
    GameRevealInspection,
    GameRevealNight,
    GameRevealPlayer,
    GameRevealResult,
    GameRevealVote,
    GameRunCreate,
    GameRunResult,
    GameRunUpdate,
    GameStatus,
    GameTimelineResult,
    GameUseCaseConfig,
    GameUseCaseDependencies,
    GetGameRevealQuery,
    GetGameRunQuery,
    GetGameTimelineQuery,
    GetPlayerObservationQuery,
    ListGameRunsQuery,
    ListGameRunsResult,
    PlayerActionCommand,
    PlayerActionResult,
    PlayerObservationResult,
    StoredGameRun,
)
from werewolf_agent.usecase.jobs.telemetry import TelemetryEvent, TelemetrySink


@dataclass(frozen=True)
class RequestedPlayer:
    """Resolved player seat requested for a game."""

    id: str
    name: str
    agent_type: str


def create_game_run(
    command: CreateGameCommand,
    *,
    dependencies: GameUseCaseDependencies,
) -> GameRunResult:
    """Create and persist one deterministic game."""
    game_id = uuid4()
    requested_players = _requested_player_configs(command, dependencies.config)
    selected_profiles = select_players(
        dependencies.llm_definitions.players,
        player_count=len(requested_players),
        seed=command.seed,
    )
    players = [
        Player(
            id=player.id,
            name=display_name_for(player.name, selected_profile),
        )
        for player, selected_profile in zip(requested_players, selected_profiles, strict=True)
    ]
    control_tokens = _control_tokens_for(command)
    config = _domain_config(
        command,
        player_count=len(players),
        rules=local_rules_to_domain(command.rules),
        roles=to_role_catalog(dependencies.game_definitions.roles),
    )
    run_config = {
        "player_agent_types": {
            player.id: requested_player.agent_type
            for player, requested_player in zip(players, requested_players, strict=True)
        },
        "player_profile_ids": profile_ids_by_player(
            [player.id for player in players],
            selected_profiles,
        ),
    }
    snapshot, events = start_game(config, players, random.Random(command.seed))
    public_state = public_state_payload_from_snapshot(
        snapshot,
        game_id=str(game_id),
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


def get_game_reveal(
    query: GetGameRevealQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> GameRevealResult:
    """Return full game information for the dedicated observer reveal boundary."""
    game_id = _parse_game_id(query.game_id)
    run = dependencies.repository.get(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))

    snapshot = GameSnapshot.model_validate(run.private_state)
    pending_actions = PendingActions.model_validate(run.pending_actions)
    alive_player_ids = [
        player.id for player in snapshot.players.values() if player.status is PlayerStatus.ALIVE
    ]
    eliminated_player_ids = [
        player.id for player in snapshot.players.values() if player.status is PlayerStatus.DEAD
    ]
    return GameRevealResult(
        game_id=str(run.id),
        status=run.status,
        phase=cast(GamePhase, snapshot.phase.value),
        day=snapshot.day,
        version=run.version,
        seed=run.seed,
        role_counts=dict(snapshot.config.role_counts),
        rules=snapshot.config.rules,
        players=[
            GameRevealPlayer(
                id=player.id,
                name=player.name,
                role=str(player.role or ""),
                faction=_player_faction(snapshot, player),
                alive=player.status is PlayerStatus.ALIVE,
                status=player.status.value,
                eliminated_day=player.eliminated_day,
                killed_night=player.killed_night,
            )
            for player in snapshot.players.values()
        ],
        alive_player_ids=alive_player_ids,
        eliminated_player_ids=eliminated_player_ids,
        winner=winner_from_snapshot(snapshot),
        pending_votes=[_reveal_action(action) for action in pending_actions.votes.values()],
        pending_night_actions=[
            _reveal_action(action) for action in pending_actions.night_actions.values()
        ],
        votes=[
            GameRevealVote(
                day=vote.day,
                votes=dict(vote.votes),
                counts=dict(vote.counts),
                tied_player_ids=list(vote.tied_player_ids),
                missing_voter_ids=list(vote.missing_voter_ids),
                eliminated_player_id=vote.eliminated_player_id,
                tie_break_policy=vote.tie_break_policy,
            )
            for vote in snapshot.history.votes
        ],
        nights=[
            GameRevealNight(
                day=night.day,
                attacked_player_id=night.attacked_player_id,
                protected_player_id=night.protected_player_id,
                killed_player_id=night.killed_player_id,
                inspections=[
                    GameRevealInspection(
                        seer_id=inspection.seer_id,
                        target_id=inspection.target_id,
                        target_role=inspection.target_role,
                        target_faction=inspection.target_faction,
                    )
                    for inspection in night.inspections
                ],
            )
            for night in snapshot.history.nights
        ],
    )


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
    human_player_ids = _human_player_ids(run.config)
    if _manual_input_required(snapshot, pending_actions, human_player_ids):
        raise GamePhaseError(
            MESSAGE_MANUAL_INPUT_REQUIRED,
            context={
                "game_id": str(run.id),
                "phase": snapshot.phase.value,
                "day": snapshot.day,
            },
        )
    dependencies.telemetry.record(
        TelemetryEvent(
            "game.phase.drive_started",
            level="DEBUG",
            fields=_telemetry_state_fields(run, snapshot),
        )
    )
    snapshot, pending_actions, action_events = _drive_current_phase(
        snapshot,
        seed=run.seed,
        version=run.version,
        pending_actions=pending_actions,
        agent_factory=langchain_agent_factory(
            dependencies.llm_provider_config,
            definitions=dependencies.llm_definitions,
            profile_ids_by_player=_player_profile_ids(run.config),
        ),
        agent_type=dependencies.config.supported_agent_type,
        human_player_ids=human_player_ids,
        telemetry=dependencies.telemetry,
    )
    dependencies.telemetry.record(
        TelemetryEvent(
            "game.phase.drive_completed",
            level="DEBUG",
            fields={
                **_telemetry_snapshot_fields(snapshot, version=run.version),
                "event_count": len(action_events),
            },
        )
    )
    dependencies.telemetry.record(
        TelemetryEvent(
            "game.phase.advance_started",
            level="DEBUG",
            fields=_telemetry_snapshot_fields(snapshot, version=run.version),
        )
    )
    next_snapshot, _next_pending_actions, phase_events = advance_phase(
        snapshot,
        pending_actions,
        runtime_rng,
    )
    dependencies.telemetry.record(
        TelemetryEvent(
            "game.phase.advance_completed",
            level="DEBUG",
            fields={
                **_telemetry_snapshot_fields(next_snapshot, version=run.version + 1),
                "event_count": len(phase_events),
            },
        )
    )
    next_public_state = public_state_payload_from_snapshot(
        next_snapshot,
        game_id=str(run.id),
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
    latest_turn_sequence = dependencies.repository.latest_public_turn_sequence(updated_run.id)
    records = dependencies.repository.append_events(
        updated_run.id,
        events_to_create([*action_events, *phase_events]),
    )
    turns = dependencies.repository.list_public_turns(
        updated_run.id,
        after=latest_turn_sequence,
        limit=max(len(records), 1),
    )
    return AdvanceGameRunResult(
        game_id=str(updated_run.id),
        status=updated_run.status,
        state=public_state_payload_from_run(updated_run),
        timeline=[public_turn_payload_from_record(record) for record in turns],
    )


def advance_until_input(
    command: AdvanceUntilInputCommand,
    *,
    dependencies: GameUseCaseDependencies,
) -> AdvanceUntilInputResult:
    """Advance a game until a manual player can act, completion, or step limit."""
    game_id = _parse_game_id(command.game_id)
    timeline: list[dict[str, Any]] = []
    steps = 0
    while True:
        run = dependencies.repository.get_for_update(game_id)
        if run is None:
            raise GameNotFoundError(str(game_id))

        snapshot = GameSnapshot.model_validate(run.private_state)
        pending_actions = PendingActions.model_validate(run.pending_actions)
        if run.status == "completed":
            return AdvanceUntilInputResult(
                game_id=str(run.id),
                status=run.status,
                state=public_state_payload_from_run(run),
                timeline=timeline,
                stop_reason="completed",
                steps=steps,
            )
        if _manual_input_required(snapshot, pending_actions, _human_player_ids(run.config)):
            return AdvanceUntilInputResult(
                game_id=str(run.id),
                status=run.status,
                state=public_state_payload_from_run(run),
                timeline=timeline,
                stop_reason="manual_input_required",
                steps=steps,
            )
        if steps >= command.max_steps:
            return AdvanceUntilInputResult(
                game_id=str(run.id),
                status=run.status,
                state=public_state_payload_from_run(run),
                timeline=timeline,
                stop_reason="hit_limit",
                steps=steps,
            )

        advanced = advance_game_run(
            AdvanceGameRunCommand(game_id=game_id),
            dependencies=dependencies,
        )
        timeline.extend(advanced.timeline)
        steps += 1


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
    pending_actions = PendingActions.model_validate(run.pending_actions)
    observation = observe(snapshot, pending_actions, query.player_id)
    return PlayerObservationResult(
        game_id=str(run.id),
        player_id=query.player_id,
        observation=observation.model_dump(mode="json"),
    )


def submit_player_action(
    command: PlayerActionCommand,
    *,
    dependencies: GameUseCaseDependencies,
) -> PlayerActionResult:
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
        type=_action_type(command.type),
        player_id=command.player_id,
        target_id=command.target_id,
        message=command.message,
        reason=command.reason,
    )
    next_snapshot, next_pending_actions, events = submit_action(snapshot, pending_actions, action)
    dependencies.telemetry.record(
        TelemetryEvent(
            "game.manual_action.accepted",
            level="INFO",
            fields={
                **_telemetry_snapshot_fields(next_snapshot, version=run.version),
                "has_target": command.target_id is not None,
                "has_message": bool(command.message),
                "event_count": len(events),
            },
        )
    )
    next_public_state = public_state_payload_from_snapshot(
        next_snapshot,
        game_id=str(run.id),
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
    latest_turn_sequence = dependencies.repository.latest_public_turn_sequence(updated_run.id)
    records = dependencies.repository.append_events(updated_run.id, events_to_create(events))
    turns = dependencies.repository.list_public_turns(
        updated_run.id,
        after=latest_turn_sequence,
        limit=max(len(records), 1),
    )
    return PlayerActionResult(
        game_id=str(updated_run.id),
        player_id=command.player_id,
        state=public_state_payload_from_run(updated_run),
        timeline=[public_turn_payload_from_record(record) for record in turns],
    )


def get_game_timeline(
    query: GetGameTimelineQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> GameTimelineResult:
    """List public timeline records after a sequence number."""
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
    return GameTimelineResult(
        game_id=str(run.id),
        items=[public_turn_payload_from_record(record) for record in records],
        next_after=next_after,
    )


def _player_faction(snapshot: GameSnapshot, player: Player) -> str:
    if player.role is None:
        return ""
    return snapshot.config.roles.faction_for_role(player.role)


def _reveal_action(action: Action) -> GameRevealAction:
    return GameRevealAction(
        player_id=action.player_id,
        type=action.type.value,
        target_id=action.target_id,
        message=action.message,
    )


def _parse_game_id(value: str | UUID) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(value)
    except ValueError as exc:
        raise InvalidGameIdError(MESSAGE_GAME_ID_MUST_BE_VALID_UUID) from exc


def _action_type(value: str) -> ActionType:
    try:
        return ActionType(value)
    except ValueError as exc:
        raise GameError(
            f"Unsupported action type: {value}",
            context={"action_type": value},
        ) from exc


def _domain_config(
    command: CreateGameCommand,
    *,
    player_count: int,
    rules: LocalRules,
    roles: RoleCatalog,
) -> GameConfig:
    return GameConfig(
        player_count=player_count,
        role_counts={str(role): count for role, count in command.role_counts.items()},
        rules=rules,
        roles=roles,
    )


def _requested_player_configs(
    command: CreateGameCommand,
    config: GameUseCaseConfig,
) -> list[RequestedPlayer]:
    player_count = command.player_count
    if player_count < config.min_players or player_count > config.max_players:
        raise GameError(message_player_count_between(config.min_players, config.max_players))
    return [
        RequestedPlayer(
            id=f"player-{index}",
            name=f"Player {index}",
            agent_type=(
                "human"
                if f"player-{index}" == command.human_player_id
                else config.supported_agent_type
            ),
        )
        for index in range(1, player_count + 1)
    ]


def _control_tokens_for(command: CreateGameCommand) -> dict[str, str]:
    if command.human_player_id is None:
        return {}
    return {command.human_player_id: secrets.token_urlsafe(32)}


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


def _player_profile_ids(config: Mapping[str, object]) -> dict[str, str]:
    profile_ids = config.get("player_profile_ids")
    if not isinstance(profile_ids, dict):
        return {}
    return {str(player_id): str(profile_id) for player_id, profile_id in profile_ids.items()}


def _manual_input_required(
    snapshot: GameSnapshot,
    pending_actions: PendingActions,
    human_player_ids: set[str],
) -> bool:
    return any(
        player_id in snapshot.players
        and bool(observe(snapshot, pending_actions, player_id).available_actions)
        for player_id in human_player_ids
    )


def _drive_current_phase(
    snapshot: GameSnapshot,
    *,
    seed: int | None,
    version: int,
    pending_actions: PendingActions,
    agent_factory: AgentFactory,
    agent_type: str,
    human_player_ids: set[str],
    telemetry: TelemetrySink,
) -> tuple[GameSnapshot, PendingActions, list[DomainEvent]]:
    current_snapshot = snapshot
    current_pending_actions = pending_actions
    events: list[DomainEvent] = []
    turn_count = 1
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
            observation = observe(current_snapshot, current_pending_actions, player.id)
            action = agent.act(observation)
            telemetry.record(
                TelemetryEvent(
                    "game.agent_action.generated",
                    level="DEBUG",
                    fields={
                        **_telemetry_snapshot_fields(current_snapshot, version=version),
                        "agent_type": agent_type,
                        "candidate_count": _candidate_count(observation.players, player.id),
                        "turn_index": turn,
                    },
                )
            )
            current_snapshot, current_pending_actions, action_events = submit_action(
                current_snapshot,
                current_pending_actions,
                action,
            )
            events.extend(action_events)
    return current_snapshot, current_pending_actions, events


def _telemetry_state_fields(run: StoredGameRun, snapshot: GameSnapshot) -> dict[str, object]:
    return {
        **_telemetry_snapshot_fields(snapshot, version=run.version),
        "game_id": str(run.id),
        "game_status": run.status,
    }


def _telemetry_snapshot_fields(snapshot: GameSnapshot, *, version: int) -> dict[str, object]:
    return {
        "game_phase": snapshot.phase.value,
        "game_day": snapshot.day,
        "game_version": version,
    }


def _candidate_count(players: Sequence[Player], player_id: str) -> int:
    return sum(
        1 for player in players if player.status is PlayerStatus.ALIVE and player.id != player_id
    )


def _runtime_seed(seed: int | None, version: int) -> int:
    return (seed or 0) + version * 1009


def _agent_seed(seed: int | None, version: int, index: int, turn: int = 0) -> int:
    return (seed or 0) + version * 1009 + index * 131 + turn * 1709
