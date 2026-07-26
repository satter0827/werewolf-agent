"""Stateless handlers connecting user requirements to the domain."""

from __future__ import annotations

from typing import cast

from werewolf_agent.application.domain_codec import domain_to_data
from werewolf_agent.application.errors import GameError, GameNotFoundError, GamePhaseError
from werewolf_agent.application.handlers.common import (
    _action_from_command,
    _authorize_manual_player,
    _config_text,
    _narration_mode,
    _narration_profile,
    _parse_game_id,
    _restore_game,
    _setup_theme,
)
from werewolf_agent.application.messages import (
    MESSAGE_ADVANCE_JOB_STATE_CHANGED,
    MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED,
)
from werewolf_agent.application.models import (
    ApplicationContext,
    GameRecordUpdate,
    GetPlayerObservationQuery,
    PlayerActionCommand,
    PlayerActionResult,
    PlayerObservationResult,
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


def get_player_observation(
    query: GetPlayerObservationQuery,
    *,
    dependencies: ApplicationContext,
) -> PlayerObservationResult:
    """Return one authenticated player's private observation."""
    game_id = _parse_game_id(query.game_id)
    run = dependencies.repository.get(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))
    _authorize_manual_player(
        run,
        query.player_id,
        trusted_user_id=query.trusted_user_id,
    )
    game = _restore_game(run)
    observation = game.view_for(query.player_id)
    return PlayerObservationResult(
        game_id=str(run.id),
        player_id=query.player_id,
        observation=domain_to_data(observation),
    )


def submit_player_action(
    command: PlayerActionCommand,
    *,
    dependencies: ApplicationContext,
) -> PlayerActionResult:
    """Submit one authenticated manual player action."""
    game_id = _parse_game_id(command.game_id)
    run = dependencies.repository.get_for_update(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))
    if command.expected_version is not None and run.version != command.expected_version:
        raise GamePhaseError(MESSAGE_ADVANCE_JOB_STATE_CHANGED)
    if run.status == GAME_STATUS_COMPLETED:
        raise GamePhaseError(MESSAGE_FINISHED_GAMES_CANNOT_BE_ADVANCED)

    _authorize_manual_player(
        run,
        command.player_id,
        trusted_user_id=command.trusted_user_id,
    )
    game = _restore_game(run)
    action = _action_from_command(command)
    try:
        events = game.submit(action)
        next_snapshot = game.snapshot()
        next_pending_actions = game.pending_actions
    except DomainRuleViolation as exc:
        raise GameError(str(exc), context=exc.context) from exc
    next_public_state = public_state_payload_from_snapshot(
        next_snapshot,
        game_id=str(run.id),
        version=run.version + 1,
        seed=run.seed,
        created_at=run.created_at,
        scenario_id=_config_text(run.config, "scenario_id"),
        scenario_name=_config_text(run.config, "scenario_name"),
        narration_mode=_narration_mode(run.config),
        theme=_setup_theme(run.config),
    )
    updated_run = dependencies.repository.save(
        GameRecordUpdate(
            id=run.id,
            status=cast(GameStatus, next_public_state["status"]),
            phase=cast(GamePhase, next_public_state["phase"]),
            day=cast(int, next_public_state["day"]),
            public_state=next_public_state,
            private_state=domain_to_data(next_snapshot),
            pending_actions=domain_to_data(next_pending_actions),
            version=run.version + 1,
        )
    )
    latest_turn_sequence = dependencies.repository.latest_public_turn_sequence(updated_run.id)
    records = dependencies.repository.append_events(
        updated_run.id,
        events_to_create(
            events,
            narration_profile=_narration_profile(run.config, dependencies.game_definitions),
            narration_mode=_narration_mode(run.config),
            theme=_setup_theme(run.config),
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
