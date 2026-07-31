"""Stateless handlers connecting user requirements to the domain."""

from __future__ import annotations

import random
from typing import cast

from werewolf_agent.application.domain_codec import domain_to_data
from werewolf_agent.application.errors import GameError, GameNotFoundError, GamePhaseError
from werewolf_agent.application.handlers.common import (
    _config_text,
    _manual_input_required,
    _manual_player_ids,
    _narration_mode,
    _narration_profile,
    _parse_game_id,
    _restore_game,
    _runtime_seed,
    _setup_theme,
)
from werewolf_agent.application.messages import (
    MESSAGE_ADVANCE_JOB_STATE_CHANGED,
    MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED,
    MESSAGE_MANUAL_INPUT_REQUIRED,
)
from werewolf_agent.application.models import (
    AdvanceGameCommand,
    AdvanceGameResult,
    ApplicationContext,
    ComputedAdvanceGame,
    GameRecordUpdate,
    PreparedAdvanceGame,
)
from werewolf_agent.application.projections import (
    events_to_create,
    public_state_payload_from_game,
    public_state_payload_from_snapshot,
    public_turn_payload_from_record,
)
from werewolf_agent.application.types import (
    GAME_STATUS_COMPLETED,
    GamePhase,
    GameStatus,
)
from werewolf_agent.domain import (
    RuleViolation as DomainRuleViolation,
)


def advance_game(
    command: AdvanceGameCommand,
    *,
    dependencies: ApplicationContext,
) -> AdvanceGameResult:
    """Advance one game by one business step."""
    prepared = prepare_advance_game(command, dependencies=dependencies)
    computed = run_prepared_advance(prepared, dependencies=dependencies)
    return commit_prepared_advance(computed, dependencies=dependencies)


def prepare_advance_game(
    command: AdvanceGameCommand,
    *,
    dependencies: ApplicationContext,
) -> PreparedAdvanceGame:
    """Prepare immutable advance input in a short persistence unit."""
    game_id = _parse_game_id(command.game_id)
    run = dependencies.repository.get_for_update(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))
    if command.expected_version is not None and run.version != command.expected_version:
        raise GamePhaseError(MESSAGE_ADVANCE_JOB_STATE_CHANGED)
    if run.status == GAME_STATUS_COMPLETED:
        raise GamePhaseError(MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED)

    game = _restore_game(run, dependencies)
    snapshot = game.snapshot()
    manual_player_ids = _manual_player_ids(run.config)
    if _manual_input_required(game, manual_player_ids):
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
        game=game,
        created_at=run.created_at,
    )


def run_prepared_advance(
    prepared: PreparedAdvanceGame,
    *,
    dependencies: ApplicationContext,
) -> ComputedAdvanceGame:
    """Run LLM and domain advance computation without persistence access."""
    return compute_prepared_advance(prepared)


def compute_prepared_advance(
    prepared: PreparedAdvanceGame,
) -> ComputedAdvanceGame:
    """Compute an advance using definition data without retaining application I/O."""
    game = prepared.game
    runtime_rng = random.Random(_runtime_seed(prepared.seed, prepared.version))
    action_events = list(prepared.domain_events)
    try:
        phase_events = game.advance(runtime_rng)
        next_snapshot = game.snapshot()
    except DomainRuleViolation as exc:
        raise GameError(str(exc), context=exc.context) from exc
    next_public_state = public_state_payload_from_snapshot(
        next_snapshot,
        game_id=prepared.game_id,
        version=prepared.version + 1,
        seed=prepared.seed,
        created_at=prepared.created_at,
        scenario_id=_config_text(prepared.config, "scenario_id"),
        scenario_name=_config_text(prepared.config, "scenario_name"),
        narration_mode=_narration_mode(prepared.config),
        theme=_setup_theme(prepared.config),
    )
    return ComputedAdvanceGame(
        game_id=prepared.game_id,
        expected_version=prepared.version,
        status=cast(GameStatus, next_public_state["status"]),
        phase=cast(GamePhase, next_public_state["phase"]),
        day=cast(int, next_public_state["day"]),
        public_state=next_public_state,
        private_state=domain_to_data(next_snapshot),
        pending_actions=domain_to_data(game.pending_actions),
        events=events_to_create(
            [*action_events, *phase_events],
            narration_profile=_narration_profile(prepared.config),
            narration_mode=_narration_mode(prepared.config),
            theme=_setup_theme(prepared.config),
        ),
    )


def commit_prepared_advance(
    computed: ComputedAdvanceGame,
    *,
    dependencies: ApplicationContext,
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
