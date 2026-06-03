"""Internal implementations for game use case jobs."""

from __future__ import annotations

import hashlib
import hmac
import random
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

from werewolf_agent.commons.shared.constants import (
    DEFAULT_NARRATION_MODE,
    MIN_PAGE_LIMIT,
    NARRATION_MODE_CHOICES,
    NarrationMode,
)
from werewolf_agent.commons.shared.definitions import (
    GameDefinitions,
    GameRoleDefinitions,
    LlmDefinitions,
    NarrationProfileDefinition,
    PlayerProfile,
    PlayerRoster,
    RoleDefinition,
)
from werewolf_agent.commons.shared.messages import (
    MESSAGE_ADVANCE_JOB_STATE_CHANGED,
    MESSAGE_CHARACTER_ASSIGNMENTS_CONTAIN_UNKNOWN_CHARACTER_IDS,
    MESSAGE_CHARACTER_ASSIGNMENTS_CONTAIN_UNKNOWN_GENERATED_PLAYER_IDS,
    MESSAGE_CUSTOM_CHARACTERS_CONFLICT_WITH_DEFAULT_CHARACTER_IDS,
    MESSAGE_CUSTOM_CHARACTERS_CONFLICT_WITH_PLAYER_ROSTER,
    MESSAGE_CUSTOM_ROLES_CONFLICT_WITH_DEFAULT_ROLE_IDS,
    MESSAGE_CUSTOM_ROLES_CONTAIN_UNKNOWN_ABILITIES,
    MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED,
    MESSAGE_GAME_ID_MUST_BE_VALID_UUID,
    MESSAGE_INVALID_MANUAL_TOKEN,
    MESSAGE_MANUAL_INPUT_REQUIRED,
    MESSAGE_PLAYER_IS_NOT_MANUAL,
    MESSAGE_PLAYER_ROSTER_NOT_ENOUGH_ENABLED_PLAYERS,
    message_field_must_be_between,
    message_player_count_between,
    message_unknown_agent_strategy,
    message_unknown_scenario,
    message_unknown_setup_preset,
    message_unsupported_action_type,
)
from werewolf_agent.commons.shared.validation import (
    generated_player_id,
    generated_player_ids,
    generated_player_name,
    non_blank,
)
from werewolf_agent.contracts import (
    GAME_STATUS_COMPLETED,
    GameError,
    GameNotFoundError,
    GamePhase,
    GamePhaseError,
    GameStatus,
    InvalidGameIdError,
    InvalidManualTokenError,
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
from werewolf_agent.domain.llm.models import AgentScenario
from werewolf_agent.usecase.internal.agents import AgentFactory, langchain_agent_factory
from werewolf_agent.usecase.internal.definitions import local_rules_to_domain, to_role_catalog
from werewolf_agent.usecase.internal.players import (
    SelectedPlayerProfile,
    display_name_for,
    profile_ids_by_player,
    select_players,
)
from werewolf_agent.usecase.internal.projections import (
    events_to_create,
    public_game_summary_payload_from_record,
    public_state_payload_from_game,
    public_state_payload_from_snapshot,
    public_turn_payload_from_record,
    winner_from_snapshot,
)
from werewolf_agent.usecase.jobs.games import (
    AdvanceGameCommand,
    AdvanceGameResult,
    ComputedAdvanceGame,
    CreateGameCommand,
    GameListResult,
    GameRecordCreate,
    GameRecordUpdate,
    GameResult,
    GameRevealAction,
    GameRevealInspection,
    GameRevealNight,
    GameRevealPlayer,
    GameRevealResult,
    GameRevealVote,
    GameTimelineResult,
    GameUseCaseConfig,
    GameUseCaseDependencies,
    GetGameQuery,
    GetGameRevealQuery,
    GetPlayerObservationQuery,
    ListGamesQuery,
    ListTimelineQuery,
    ManualPlayerCredential,
    PlayerActionCommand,
    PlayerActionResult,
    PlayerObservationResult,
    PreparedAdvanceGame,
    StoredGame,
)
from werewolf_agent.usecase.jobs.telemetry import TelemetryEvent, TelemetrySink


@dataclass(frozen=True)
class RequestedPlayer:
    """Resolved player seat requested for a game."""

    id: str
    name: str
    agent_type: str


def create_game(
    command: CreateGameCommand,
    *,
    dependencies: GameUseCaseDependencies,
) -> GameResult:
    """Create and persist one deterministic game."""
    game_id = uuid4()
    requested_players = _requested_player_configs(command, dependencies.config)
    game_definitions = _game_definitions_for(command, dependencies.game_definitions)
    llm_definitions = _llm_definitions_for(command, dependencies.llm_definitions)
    selected_profiles = _select_player_profiles(
        llm_definitions.players,
        player_count=len(requested_players),
        seed=command.seed,
        character_assignments=command.character_assignments,
    )
    players = [
        Player(
            id=player.id,
            name=display_name_for(player.name, selected_profile),
        )
        for player, selected_profile in zip(requested_players, selected_profiles, strict=True)
    ]
    manual_player = _manual_player_credential_for(command)
    config = _domain_config(
        command,
        player_count=len(players),
        rules=local_rules_to_domain(command.rules),
        roles=to_role_catalog(game_definitions.roles),
    )
    scenario_config = _scenario_config(command, game_definitions)
    agent_strategy_id = _agent_strategy_id(
        command.agent_strategy_id,
        definitions=llm_definitions,
        default_strategy_id=dependencies.llm_provider_config.default_agent_strategy_id,
    )
    run_config = {
        **scenario_config,
        "narration_mode": command.narration_mode,
        "agent_strategy_id": agent_strategy_id,
        "custom_roles": [definition.model_dump(mode="json") for definition in command.custom_roles],
        "custom_characters": [
            definition.model_dump(mode="json") for definition in command.custom_characters
        ],
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
        scenario_id=_config_text(scenario_config, "scenario_id"),
        scenario_name=_config_text(scenario_config, "scenario_name"),
        narration_mode=command.narration_mode,
    )
    run = dependencies.repository.create(
        GameRecordCreate(
            id=game_id,
            status=cast(GameStatus, public_state["status"]),
            phase=cast(GamePhase, public_state["phase"]),
            day=cast(int, public_state["day"]),
            seed=command.seed,
            config=run_config,
            public_state=public_state,
            private_state=snapshot.model_dump(mode="json"),
            pending_actions=PendingActions().model_dump(mode="json"),
            manual_token_hashes=_manual_token_hashes(manual_player),
            version=1,
        )
    )
    dependencies.repository.append_events(
        run.id,
        events_to_create(
            events,
            narration_profile=_narration_profile(run_config, game_definitions),
            narration_mode=command.narration_mode,
        ),
    )
    return GameResult(
        game_id=str(run.id),
        state=public_state_payload_from_game(run),
        manual_player=manual_player,
    )


def get_game(
    query: GetGameQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> GameResult:
    """Return the current public state for one game."""
    game_id = _parse_game_id(query.game_id)
    run = dependencies.repository.get(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))
    return GameResult(game_id=str(run.id), state=public_state_payload_from_game(run))


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
        scenario_id=_config_text(run.config, "scenario_id"),
        scenario_name=_config_text(run.config, "scenario_name"),
        narration_mode=_narration_mode(run.config),
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


def list_games(
    query: ListGamesQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> GameListResult:
    """Return a page of public game summaries."""
    limit = _page_limit(
        query.limit,
        default=dependencies.config.game_list_default_limit,
        maximum=dependencies.config.game_list_max_limit,
        field_name="limit",
    )
    records = dependencies.repository.list_game_summaries(
        status=query.status,
        limit=limit,
        offset=query.offset,
    )
    next_offset = query.offset + len(records) if len(records) == limit else None
    return GameListResult(
        games=[public_game_summary_payload_from_record(record) for record in records],
        next_offset=next_offset,
    )


def advance_game(
    command: AdvanceGameCommand,
    *,
    dependencies: GameUseCaseDependencies,
) -> AdvanceGameResult:
    """Advance one game by one business step."""
    prepared = prepare_advance_game(command, dependencies=dependencies)
    computed = run_prepared_advance(prepared, dependencies=dependencies)
    return commit_prepared_advance(computed, dependencies=dependencies)


def prepare_advance_game(
    command: AdvanceGameCommand,
    *,
    dependencies: GameUseCaseDependencies,
) -> PreparedAdvanceGame:
    """Prepare immutable advance input in a short persistence unit."""
    game_id = _parse_game_id(command.game_id)
    run = dependencies.repository.get_for_update(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))
    if run.status == GAME_STATUS_COMPLETED:
        raise GamePhaseError(MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED)

    snapshot = GameSnapshot.model_validate(run.private_state)
    pending_actions = PendingActions.model_validate(run.pending_actions)
    manual_player_ids = _manual_player_ids(run.config)
    if _manual_input_required(snapshot, pending_actions, manual_player_ids):
        raise GamePhaseError(
            MESSAGE_MANUAL_INPUT_REQUIRED,
            context={
                "game_id": str(run.id),
                "phase": snapshot.phase.value,
                "day": snapshot.day,
            },
        )
    return PreparedAdvanceGame(
        game_id=str(run.id),
        version=run.version,
        seed=run.seed,
        config=dict(run.config),
        private_state=snapshot.model_dump(mode="json"),
        pending_actions=pending_actions.model_dump(mode="json"),
        created_at=run.created_at,
    )


def run_prepared_advance(
    prepared: PreparedAdvanceGame,
    *,
    dependencies: GameUseCaseDependencies,
) -> ComputedAdvanceGame:
    """Run LLM and domain advance computation without persistence access."""
    snapshot = GameSnapshot.model_validate(prepared.private_state)
    runtime_rng = random.Random(_runtime_seed(prepared.seed, prepared.version))
    pending_actions = PendingActions.model_validate(prepared.pending_actions)
    manual_player_ids = _manual_player_ids(prepared.config)
    agent_strategy_id = _agent_strategy_id_from_config(
        prepared.config,
        dependencies=dependencies,
    )
    dependencies.telemetry.record(
        TelemetryEvent(
            "game.phase.drive_started",
            level="DEBUG",
            fields={
                **_telemetry_snapshot_fields(snapshot, version=prepared.version),
                "game_id": prepared.game_id,
            },
        )
    )
    snapshot, pending_actions, action_events = _drive_current_phase(
        snapshot,
        seed=prepared.seed,
        version=prepared.version,
        pending_actions=pending_actions,
        agent_factory=langchain_agent_factory(
            dependencies.llm_provider_config,
            definitions=_llm_definitions_for_game(prepared.config, dependencies.llm_definitions),
            agent_strategy_id=agent_strategy_id,
            profile_ids_by_player=_player_profile_ids(prepared.config),
            scenario=_agent_scenario(prepared.config),
            trace_sink=dependencies.llm_trace_sink,
        ),
        agent_type=dependencies.config.supported_agent_type,
        manual_player_ids=manual_player_ids,
        telemetry=dependencies.telemetry,
    )
    dependencies.telemetry.record(
        TelemetryEvent(
            "game.phase.drive_completed",
            level="DEBUG",
            fields={
                **_telemetry_snapshot_fields(snapshot, version=prepared.version),
                "event_count": len(action_events),
            },
        )
    )
    dependencies.telemetry.record(
        TelemetryEvent(
            "game.phase.advance_started",
            level="DEBUG",
            fields=_telemetry_snapshot_fields(snapshot, version=prepared.version),
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
                **_telemetry_snapshot_fields(next_snapshot, version=prepared.version + 1),
                "event_count": len(phase_events),
            },
        )
    )
    next_public_state = public_state_payload_from_snapshot(
        next_snapshot,
        game_id=prepared.game_id,
        version=prepared.version + 1,
        seed=prepared.seed,
        created_at=prepared.created_at,
        scenario_id=_config_text(prepared.config, "scenario_id"),
        scenario_name=_config_text(prepared.config, "scenario_name"),
        narration_mode=_narration_mode(prepared.config),
    )
    return ComputedAdvanceGame(
        game_id=prepared.game_id,
        expected_version=prepared.version,
        status=cast(GameStatus, next_public_state["status"]),
        phase=cast(GamePhase, next_public_state["phase"]),
        day=cast(int, next_public_state["day"]),
        public_state=next_public_state,
        private_state=next_snapshot.model_dump(mode="json"),
        pending_actions=_next_pending_actions.model_dump(mode="json"),
        events=events_to_create(
            [*action_events, *phase_events],
            narration_profile=_narration_profile(prepared.config, dependencies.game_definitions),
            narration_mode=_narration_mode(prepared.config),
        ),
    )


def commit_prepared_advance(
    computed: ComputedAdvanceGame,
    *,
    dependencies: GameUseCaseDependencies,
) -> AdvanceGameResult:
    """Persist a computed advance result after checking the game version."""
    game_id = _parse_game_id(computed.game_id)
    run = dependencies.repository.get_for_update(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))
    if run.version != computed.expected_version:
        raise GamePhaseError(MESSAGE_ADVANCE_JOB_STATE_CHANGED)
    updated_run = dependencies.repository.save(
        GameRecordUpdate(
            id=game_id,
            status=computed.status,
            phase=computed.phase,
            day=computed.day,
            public_state=computed.public_state,
            private_state=computed.private_state,
            pending_actions=computed.pending_actions,
            version=computed.expected_version + 1,
        )
    )
    latest_turn_sequence = dependencies.repository.latest_public_turn_sequence(updated_run.id)
    records = dependencies.repository.append_events(
        updated_run.id,
        computed.events,
    )
    turns = dependencies.repository.list_public_turns(
        updated_run.id,
        after=latest_turn_sequence,
        limit=max(len(records), 1),
    )
    return AdvanceGameResult(
        game_id=str(updated_run.id),
        status=updated_run.status,
        state=public_state_payload_from_game(updated_run),
        timeline=[public_turn_payload_from_record(record) for record in turns],
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
    _authorize_manual_player(
        run,
        query.player_id,
        query.manual_token,
        trusted_user_id=query.trusted_user_id,
    )
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
    if run.status == GAME_STATUS_COMPLETED:
        raise GamePhaseError(MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED)

    _authorize_manual_player(
        run,
        command.player_id,
        command.manual_token,
        trusted_user_id=command.trusted_user_id,
    )
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
        scenario_id=_config_text(run.config, "scenario_id"),
        scenario_name=_config_text(run.config, "scenario_name"),
        narration_mode=_narration_mode(run.config),
    )
    updated_run = dependencies.repository.save(
        GameRecordUpdate(
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
    records = dependencies.repository.append_events(
        updated_run.id,
        events_to_create(
            events,
            narration_profile=_narration_profile(run.config, dependencies.game_definitions),
            narration_mode=_narration_mode(run.config),
        ),
    )
    turns = dependencies.repository.list_public_turns(
        updated_run.id,
        after=latest_turn_sequence,
        limit=max(len(records), 1),
    )
    return PlayerActionResult(
        game_id=str(updated_run.id),
        player_id=command.player_id,
        state=public_state_payload_from_game(updated_run),
        timeline=[public_turn_payload_from_record(record) for record in turns],
    )


def list_timeline(
    query: ListTimelineQuery,
    *,
    dependencies: GameUseCaseDependencies,
) -> GameTimelineResult:
    """List public timeline records after a sequence number."""
    game_id = _parse_game_id(query.game_id)
    run = dependencies.repository.get(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))

    limit = _page_limit(
        query.limit,
        default=dependencies.config.timeline_default_limit,
        maximum=dependencies.config.timeline_max_limit,
        field_name="limit",
    )
    records = dependencies.repository.list_public_turns(
        run.id,
        after=query.after,
        limit=limit,
    )
    next_after = records[-1].sequence if records else query.after
    return GameTimelineResult(
        game_id=str(run.id),
        items=[public_turn_payload_from_record(record) for record in records],
        next_after=next_after,
    )


def _page_limit(
    value: int | None,
    *,
    default: int,
    maximum: int,
    field_name: str,
) -> int:
    limit = default if value is None else value
    if limit < MIN_PAGE_LIMIT or limit > maximum:
        raise GameError(
            message_field_must_be_between(field_name, MIN_PAGE_LIMIT, maximum),
            context={field_name: limit, "max_limit": maximum},
        )
    return limit


def _game_definitions_for(
    command: CreateGameCommand,
    definitions: GameDefinitions,
) -> GameDefinitions:
    if not command.custom_roles:
        return definitions

    custom_role_ids = {definition.id for definition in command.custom_roles}
    conflicts = sorted(custom_role_ids & set(definitions.roles.roles))
    if conflicts:
        raise GameError(
            MESSAGE_CUSTOM_ROLES_CONFLICT_WITH_DEFAULT_ROLE_IDS,
            context={"role_ids": conflicts},
        )

    known_abilities = set(definitions.catalog.abilities)
    unknown_abilities = sorted(
        {
            ability
            for definition in command.custom_roles
            for ability in definition.abilities
            if ability not in known_abilities
        }
    )
    if unknown_abilities:
        raise GameError(
            MESSAGE_CUSTOM_ROLES_CONTAIN_UNKNOWN_ABILITIES,
            context={"abilities": unknown_abilities},
        )

    roles = dict(definitions.roles.roles)
    roles.update(
        {
            definition.id: RoleDefinition(
                faction=definition.faction,
                abilities=tuple(definition.abilities),
                label=definition.name,
                description=definition.description or None,
                difficulty=definition.difficulty,
            )
            for definition in command.custom_roles
        }
    )
    return definitions.model_copy(
        update={
            "roles": GameRoleDefinitions(
                roles=roles,
                default_role_counts=definitions.roles.default_role_counts,
            )
        }
    )


def _llm_definitions_for(
    command: CreateGameCommand,
    definitions: LlmDefinitions,
) -> LlmDefinitions:
    if not command.custom_characters:
        return definitions

    custom_character_ids = {definition.id for definition in command.custom_characters}
    conflicts = sorted(custom_character_ids & set(definitions.players.players))
    if conflicts:
        raise GameError(
            MESSAGE_CUSTOM_CHARACTERS_CONFLICT_WITH_DEFAULT_CHARACTER_IDS,
            context={"character_ids": conflicts},
        )

    players = dict(definitions.players.players)
    players.update(
        {
            definition.id: PlayerProfile(
                name=definition.name,
                age=definition.age,
                gender=definition.gender,
                personality=definition.personality,
                speaking_style=definition.speaking_style,
                reasoning_style=definition.reasoning_style,
                risk_tolerance=definition.risk_tolerance,
            )
            for definition in command.custom_characters
        }
    )
    return _llm_definitions_with_players(definitions, players)


def _llm_definitions_for_game(
    config: Mapping[str, object],
    definitions: LlmDefinitions,
) -> LlmDefinitions:
    raw_items = config.get("custom_characters")
    if not isinstance(raw_items, list):
        return definitions

    players = dict(definitions.players.players)
    for raw_item in raw_items:
        if not isinstance(raw_item, Mapping):
            continue
        profile_id = non_blank(str(raw_item.get("id", "")), "custom character id")
        profile_payload = {str(key): value for key, value in raw_item.items() if key != "id"}
        players[profile_id] = PlayerProfile.model_validate(profile_payload)
    return _llm_definitions_with_players(definitions, players)


def _llm_definitions_with_players(
    definitions: LlmDefinitions,
    players: dict[str, PlayerProfile],
) -> LlmDefinitions:
    try:
        roster = PlayerRoster(players=players)
    except ValueError as exc:
        raise GameError(MESSAGE_CUSTOM_CHARACTERS_CONFLICT_WITH_PLAYER_ROSTER) from exc
    return definitions.model_copy(update={"players": roster})


def _select_player_profiles(
    roster: PlayerRoster,
    *,
    player_count: int,
    seed: int | None,
    character_assignments: Mapping[str, str],
) -> list[SelectedPlayerProfile]:
    if not character_assignments:
        return select_players(roster, player_count=player_count, seed=seed)

    valid_player_ids = generated_player_ids(player_count)
    unknown_players = sorted(set(character_assignments) - valid_player_ids)
    if unknown_players:
        raise GameError(
            MESSAGE_CHARACTER_ASSIGNMENTS_CONTAIN_UNKNOWN_GENERATED_PLAYER_IDS,
            context={"player_ids": unknown_players},
        )

    unknown_profiles = sorted(set(character_assignments.values()) - set(roster.players))
    if unknown_profiles:
        raise GameError(
            MESSAGE_CHARACTER_ASSIGNMENTS_CONTAIN_UNKNOWN_CHARACTER_IDS,
            context={"character_ids": unknown_profiles},
        )

    assigned_profile_ids = set(character_assignments.values())
    remaining = [
        (profile_id, profile)
        for profile_id, profile in sorted(roster.players.items())
        if profile_id not in assigned_profile_ids
    ]
    missing_count = player_count - len(character_assignments)
    if missing_count > len(remaining):
        raise GameError(
            MESSAGE_PLAYER_ROSTER_NOT_ENOUGH_ENABLED_PLAYERS,
            context={"player_count": player_count, "roster_count": len(roster.players)},
        )
    rng = random.Random(seed)
    sampled = {
        generated_player_id(index): SelectedPlayerProfile(profile_id=profile_id, profile=profile)
        for index, (profile_id, profile) in enumerate(
            rng.sample(remaining, missing_count),
            start=1,
        )
    }
    selected: list[SelectedPlayerProfile] = []
    fallback_index = 1
    for index in range(1, player_count + 1):
        player_id = generated_player_id(index)
        assigned_id = character_assignments.get(player_id)
        if assigned_id is not None:
            selected.append(
                SelectedPlayerProfile(
                    profile_id=assigned_id,
                    profile=roster.players[assigned_id],
                )
            )
            continue
        while generated_player_id(fallback_index) not in sampled:
            fallback_index += 1
        selected.append(sampled[generated_player_id(fallback_index)])
        fallback_index += 1
    return selected


def _scenario_config(command: CreateGameCommand, definitions: GameDefinitions) -> dict[str, str]:
    preset_id = command.setup_preset_id
    if preset_id is not None and preset_id not in definitions.catalog.setup_presets:
        raise GameError(
            message_unknown_setup_preset(preset_id),
            context={"setup_preset_id": preset_id},
        )
    preset = definitions.catalog.setup_presets.get(preset_id or "")
    scenario_id = command.scenario_id or (preset.scenario_id if preset is not None else None)
    if scenario_id is None:
        scenario_id = next(iter(definitions.catalog.scenarios), "")
    if not scenario_id:
        return {}
    scenario = definitions.catalog.scenarios.get(scenario_id)
    if scenario is None:
        raise GameError(message_unknown_scenario(scenario_id), context={"scenario_id": scenario_id})
    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario.label,
        "scenario_prompt_premise": scenario.prompt_premise,
        "narration_profile": scenario.narration_profile,
        "setup_preset_id": preset_id or scenario.recommended_setup_preset or "",
    }


def _narration_profile(
    config: Mapping[str, object],
    definitions: GameDefinitions,
) -> NarrationProfileDefinition | None:
    profile_id = _config_text(config, "narration_profile")
    if profile_id is None:
        return None
    return definitions.catalog.narration_profiles.get(profile_id)


def _agent_scenario(config: Mapping[str, object]) -> AgentScenario | None:
    name = _config_text(config, "scenario_name")
    premise = _config_text(config, "scenario_prompt_premise")
    if name is None or premise is None:
        return None
    return AgentScenario(name=name, premise=premise)


def _agent_strategy_id(
    value: str | None,
    *,
    definitions: LlmDefinitions,
    default_strategy_id: str,
) -> str:
    strategy_id = non_blank(value or default_strategy_id, "agent_strategy_id")
    if not definitions.agent_strategies.contains(strategy_id):
        raise GameError(
            message_unknown_agent_strategy(strategy_id),
            context={"agent_strategy_id": strategy_id},
        )
    return strategy_id


def _agent_strategy_id_from_config(
    config: Mapping[str, object],
    *,
    dependencies: GameUseCaseDependencies,
) -> str:
    value = _config_text(config, "agent_strategy_id")
    return _agent_strategy_id(
        value,
        definitions=dependencies.llm_definitions,
        default_strategy_id=dependencies.llm_provider_config.default_agent_strategy_id,
    )


def _config_text(config: Mapping[str, object], key: str) -> str | None:
    value = config.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _narration_mode(config: Mapping[str, object]) -> NarrationMode:
    value = _config_text(config, "narration_mode")
    if value in NARRATION_MODE_CHOICES:
        return cast(NarrationMode, value)
    return DEFAULT_NARRATION_MODE


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
            message_unsupported_action_type(value),
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
            id=generated_player_id(index),
            name=generated_player_name(index),
            agent_type=(
                "manual"
                if generated_player_id(index) == command.manual_player_id
                else config.supported_agent_type
            ),
        )
        for index in range(1, player_count + 1)
    ]


def _manual_player_credential_for(command: CreateGameCommand) -> ManualPlayerCredential | None:
    if command.manual_player_id is None:
        return None
    return ManualPlayerCredential(
        player_id=command.manual_player_id,
        token=secrets.token_urlsafe(32),
    )


def _manual_token_hashes(credential: ManualPlayerCredential | None) -> dict[str, str]:
    if credential is None:
        return {}
    return {credential.player_id: _hash_manual_token(credential.token)}


def _hash_manual_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _authorize_manual_player(
    run: StoredGame,
    player_id: str,
    manual_token: str,
    *,
    trusted_user_id: str | None = None,
) -> None:
    if player_id not in _manual_player_ids(run.config):
        raise InvalidManualTokenError(MESSAGE_PLAYER_IS_NOT_MANUAL)
    if trusted_user_id:
        return
    expected_hash = run.manual_token_hashes.get(player_id)
    if expected_hash is None or not hmac.compare_digest(
        expected_hash,
        _hash_manual_token(manual_token),
    ):
        raise InvalidManualTokenError(MESSAGE_INVALID_MANUAL_TOKEN)


def _manual_player_ids(config: Mapping[str, object]) -> set[str]:
    agent_types = config.get("player_agent_types")
    if not isinstance(agent_types, dict):
        return set()
    return {
        str(player_id) for player_id, agent_type in agent_types.items() if agent_type == "manual"
    }


def _player_profile_ids(config: Mapping[str, object]) -> dict[str, str]:
    profile_ids = config.get("player_profile_ids")
    if not isinstance(profile_ids, dict):
        return {}
    return {str(player_id): str(profile_id) for player_id, profile_id in profile_ids.items()}


def _manual_input_required(
    snapshot: GameSnapshot,
    pending_actions: PendingActions,
    manual_player_ids: set[str],
) -> bool:
    return any(
        player_id in snapshot.players
        and bool(observe(snapshot, pending_actions, player_id).available_actions)
        for player_id in manual_player_ids
    )


def _drive_current_phase(
    snapshot: GameSnapshot,
    *,
    seed: int | None,
    version: int,
    pending_actions: PendingActions,
    agent_factory: AgentFactory,
    agent_type: str,
    manual_player_ids: set[str],
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
            if player.id in manual_player_ids:
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


def _telemetry_state_fields(run: StoredGame, snapshot: GameSnapshot) -> dict[str, object]:
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
