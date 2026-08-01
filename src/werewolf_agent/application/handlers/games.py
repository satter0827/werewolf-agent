"""Stateless handlers connecting user requirements to the domain."""

from __future__ import annotations

import random
from collections.abc import Mapping
from typing import cast
from uuid import uuid4

from werewolf_agent.application.constants import AUTOMATED_AGENT_TYPE, MANUAL_AGENT_TYPE
from werewolf_agent.application.domain_codec import domain_to_data, game_setup_from_data
from werewolf_agent.application.errors import ConfigError, GameNotFoundError
from werewolf_agent.application.handlers.common import (
    _config_text,
    _narration_mode,
    _narration_profile,
    _page_limit,
    _parse_game_id,
    _player_faction,
    _restore_game,
    _reveal_action,
    _setup_theme,
)
from werewolf_agent.application.models import (
    ApplicationContext,
    CreateGameCommand,
    GameListResult,
    GameRecordCreate,
    GameResult,
    GameRevealInspection,
    GameRevealNight,
    GameRevealPlayer,
    GameRevealResult,
    GameRevealVote,
    GetGameQuery,
    GetGameRevealQuery,
    ListGamesQuery,
)
from werewolf_agent.application.projections import (
    events_to_create,
    public_game_summary_payload_from_record,
    public_state_payload_from_game,
    public_state_payload_from_snapshot,
    winner_from_snapshot,
)
from werewolf_agent.application.types import (
    Faction,
    GamePhase,
    GameStatus,
)
from werewolf_agent.domain import Game
from werewolf_agent.setup import LocalRulesDefinition, namespace_seed, rule_definition_from_values


def create_game(
    command: CreateGameCommand,
    *,
    dependencies: ApplicationContext,
) -> GameResult:
    """Create and persist one deterministic game."""
    game_id = uuid4()
    seed = command.seed
    setup = command.setup
    mechanics = setup.mechanics
    players = [
        {
            "id": player.player_id,
            "name": player.name,
        }
        for player in command.players
    ]
    definition = rule_definition_from_values(
        player_count=len(players),
        role_counts=mechanics.role_counts,
        rules=mechanics.rules.to_mapping(),
        roles={role_id: role.to_mapping() for role_id, role in mechanics.roles.items()},
        abilities={
            ability_id: ability.to_mapping() for ability_id, ability in mechanics.abilities.items()
        },
    )
    try:
        rules = dependencies.rule_packs.compile(command.rule_pack_provider_id, definition)
    except ValueError as exc:
        raise ConfigError("要求されたRule Packが構成されていません。") from exc
    setup_payload = setup.to_mapping()
    scenario_config = {
        "scenario_id": setup.theme.id,
        "scenario_name": setup.theme.name,
        "scenario_prompt_premise": setup.theme.premise,
    }
    run_config = {
        **scenario_config,
        "narration_mode": "standard" if setup.theme.narration_enabled else "none",
        "deliberation_level": command.deliberation_level,
        "llm_mode": command.llm_mode,
        "setup_document": setup_payload,
        "setup_checksum": command.setup_checksum,
        "mechanics_checksum": command.mechanics_checksum,
        "roster_checksum": command.roster_checksum,
        "player_agent_types": {
            player.player_id: (
                MANUAL_AGENT_TYPE
                if player.player_id == command.manual_player_id
                else AUTOMATED_AGENT_TYPE
            )
            for player in command.players
        },
        "player_profile_ids": {player.player_id: player.player_id for player in command.players},
        "player_profiles": {
            player.player_id: player.model_dump(mode="json", exclude={"player_id"})
            for player in command.players
        },
        "rule_pack_manifest": rules.manifest.to_mapping(),
    }
    game = Game.create(
        game_setup_from_data({"players": players}),
        rules=rules,
        random=random.Random(namespace_seed(seed, "role_assignment")),
    )
    snapshot = game.snapshot()
    events = list(game.creation_events)
    public_state = public_state_payload_from_snapshot(
        snapshot,
        game_id=str(game_id),
        version=1,
        scenario_id=_config_text(scenario_config, "scenario_id"),
        scenario_name=_config_text(scenario_config, "scenario_name"),
        narration_mode="standard" if setup.theme.narration_enabled else "none",
        theme=_setup_theme(run_config),
    )
    run = dependencies.repository.create(
        GameRecordCreate(
            id=game_id,
            status=cast(GameStatus, public_state["status"]),
            phase=cast(GamePhase, public_state["phase"]),
            day=cast(int, public_state["day"]),
            seed=seed,
            config=run_config,
            public_state=public_state,
            private_state=domain_to_data(snapshot),
            pending_actions=domain_to_data(snapshot.pending_actions),
            version=1,
        )
    )
    dependencies.repository.append_events(
        run.id,
        events_to_create(
            events,
            narration_profile=_narration_profile(run_config),
            narration_mode="standard" if setup.theme.narration_enabled else "none",
            theme=_setup_theme(run_config),
        ),
    )
    return GameResult(
        game_id=str(run.id),
        state=public_state_payload_from_game(run),
    )


def get_game(
    query: GetGameQuery,
    *,
    dependencies: ApplicationContext,
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
    dependencies: ApplicationContext,
) -> GameRevealResult:
    """Return full game information for the dedicated observer reveal boundary."""
    game_id = _parse_game_id(query.game_id)
    run = dependencies.repository.get(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))

    game = _restore_game(run, dependencies)
    snapshot = game.snapshot()
    pending_actions = snapshot.pending_actions
    alive_player_ids = [player.id for player in snapshot.players.values() if player.is_alive]
    eliminated_player_ids = [
        player.id for player in snapshot.players.values() if not player.is_alive
    ]
    setup_theme = _setup_theme(run.config)
    raw_role_objectives = setup_theme.get("role_objectives", {}) if setup_theme is not None else {}
    role_objectives = (
        {str(key): str(value) for key, value in raw_role_objectives.items()}
        if isinstance(raw_role_objectives, Mapping)
        else {}
    )
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
        theme=dict(setup_theme) if setup_theme is not None else None,
        role_counts=dict(snapshot.config.role_counts),
        rules=LocalRulesDefinition.from_mapping(domain_to_data(snapshot.config.rules)),
        players=[
            GameRevealPlayer(
                id=player.id,
                name=player.name,
                role=str(player.role or ""),
                identity_faction=cast(Faction, _player_faction(snapshot, player.role)),
                victory_team=cast(
                    Faction,
                    snapshot.config.roles.victory_team_for_role(str(player.role or "")),
                ),
                objective=str(role_objectives.get(str(player.role or ""), "")),
                alive=player.is_alive,
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
                        player_id=inspection.player_id,
                        ability_id=inspection.ability_id,
                        target_id=inspection.target_id,
                        target_role=inspection.target_role,
                        target_faction=cast(Faction, inspection.target_faction),
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
    dependencies: ApplicationContext,
) -> GameListResult:
    """Return a page of public game summaries."""
    limit = _page_limit(
        query.limit,
        default=dependencies.config.game_list_default_limit,
        maximum=dependencies.config.game_list_max_limit,
        field_name="limit",
    )
    records = dependencies.repository.list_game_summaries(
        user_id=query.trusted_user_id,
        status=query.status,
        limit=limit,
        offset=query.offset,
    )
    next_offset = query.offset + len(records) if len(records) == limit else None
    return GameListResult(
        games=[public_game_summary_payload_from_record(record) for record in records],
        next_offset=next_offset,
    )
