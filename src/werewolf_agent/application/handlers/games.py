"""Stateless handlers connecting user requirements to the domain."""

from __future__ import annotations

import random
from typing import cast
from uuid import uuid4

from werewolf_agent.application.definitions import (
    LocalRulesDefinition,
)
from werewolf_agent.application.handlers.common import (
    _agent_strategy_id,
    _config_text,
    _game_definitions_for,
    _narration_mode,
    _narration_profile,
    _page_limit,
    _parse_game_id,
    _player_definitions_for,
    _player_faction,
    _requested_player_configs,
    _restore_game,
    _reveal_action,
    _scenario_config,
    _select_player_profiles,
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
from werewolf_agent.application.players import (
    display_name_for,
    profile_ids_by_player,
)
from werewolf_agent.application.projections import (
    events_to_create,
    public_game_summary_payload_from_record,
    public_state_payload_from_game,
    public_state_payload_from_snapshot,
    winner_from_snapshot,
)
from werewolf_agent.contracts import (
    GameNotFoundError,
    GamePhase,
    GameStatus,
)
from werewolf_agent.domain import (
    Game,
    GameSetup,
    RuleRegistry,
    RuleSetDefinition,
)


def create_game(
    command: CreateGameCommand,
    *,
    dependencies: ApplicationContext,
) -> GameResult:
    """Create and persist one deterministic game."""
    game_id = uuid4()
    requested_players = _requested_player_configs(command, dependencies.config)
    game_definitions = _game_definitions_for(command, dependencies.game_definitions)
    player_definitions = _player_definitions_for(command, dependencies.player_definitions)
    selected_profiles = _select_player_profiles(
        player_definitions.players,
        player_count=len(requested_players),
        seed=command.seed,
        character_assignments=command.character_assignments,
    )
    players = [
        {
            "id": player.id,
            "name": display_name_for(player.name, selected_profile),
        }
        for player, selected_profile in zip(requested_players, selected_profiles, strict=True)
    ]
    rule_composition = game_definitions.rules.composition.model_dump(mode="json")
    definition = RuleSetDefinition.from_values(
        player_count=len(players),
        role_counts=command.role_counts,
        rules=command.rules.model_dump(mode="json"),
        roles={
            role_id: role.model_dump(mode="json")
            for role_id, role in game_definitions.roles.roles.items()
        },
        abilities={
            ability_id: ability.model_dump(mode="json")
            for ability_id, ability in game_definitions.catalog.abilities.items()
        },
        composition=rule_composition,
    )
    rules = RuleRegistry.standard().build(definition)
    scenario_config = _scenario_config(command, game_definitions)
    agent_strategy_id = _agent_strategy_id(
        command.agent_strategy_id,
        definitions=player_definitions,
        default_strategy_id=dependencies.config.default_agent_strategy_id,
    )
    run_config = {
        **scenario_config,
        "narration_mode": command.narration_mode,
        "agent_strategy_id": agent_strategy_id,
        "llm_mode": command.llm_mode,
        "engine_version": "0.1.0",
        "definition_snapshot": game_definitions.model_dump(mode="json"),
        "rule_composition": rule_composition,
        "custom_roles": [definition.model_dump(mode="json") for definition in command.custom_roles],
        "custom_characters": [
            definition.model_dump(mode="json") for definition in command.custom_characters
        ],
        "player_agent_types": {
            str(player["id"]): requested_player.agent_type
            for player, requested_player in zip(players, requested_players, strict=True)
        },
        "player_profile_ids": profile_ids_by_player(
            [str(player["id"]) for player in players],
            selected_profiles,
        ),
    }
    game = Game.create(
        GameSetup.model_validate({"players": players}),
        rules=rules,
        random=random.Random(command.seed),
    )
    snapshot = game.snapshot()
    events = list(game.creation_events)
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
            pending_actions=snapshot.pending_actions.model_dump(mode="json"),
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

    game = _restore_game(run)
    snapshot = game.snapshot()
    pending_actions = snapshot.pending_actions
    alive_player_ids = [player.id for player in snapshot.players.values() if player.is_alive]
    eliminated_player_ids = [
        player.id for player in snapshot.players.values() if not player.is_alive
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
        rules=LocalRulesDefinition.model_validate(snapshot.config.rules.model_dump(mode="json")),
        players=[
            GameRevealPlayer(
                id=player.id,
                name=player.name,
                role=str(player.role or ""),
                faction=_player_faction(snapshot, player.role),
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
        status=query.status,
        limit=limit,
        offset=query.offset,
    )
    next_offset = query.offset + len(records) if len(records) == limit else None
    return GameListResult(
        games=[public_game_summary_payload_from_record(record) for record in records],
        next_offset=next_offset,
    )
