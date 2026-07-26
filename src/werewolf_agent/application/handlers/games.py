"""Stateless handlers connecting user requirements to the domain."""

from __future__ import annotations

import random
import secrets
from collections.abc import Mapping
from typing import cast
from uuid import uuid4

from werewolf_agent.application.definitions import (
    LocalRulesDefinition,
    PlayerProfile,
    PlayerRoster,
    PlayerSetupDefinitions,
)
from werewolf_agent.application.domain_codec import domain_to_data, game_setup_from_data
from werewolf_agent.application.errors import GameNotFoundError
from werewolf_agent.application.handlers.common import (
    _config_text,
    _narration_mode,
    _narration_profile,
    _page_limit,
    _parse_game_id,
    _player_faction,
    _requested_player_configs,
    _restore_game,
    _reveal_action,
    _select_player_profiles,
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
from werewolf_agent.application.replay import checksum_payload
from werewolf_agent.application.rules import rule_definition_from_values
from werewolf_agent.application.types import (
    Faction,
    GamePhase,
    GameStatus,
)
from werewolf_agent.domain import (
    Game,
    RuleRegistry,
)


def create_game(
    command: CreateGameCommand,
    *,
    dependencies: ApplicationContext,
) -> GameResult:
    """Create and persist one deterministic game."""
    game_id = uuid4()
    seed = command.seed if command.seed is not None else secrets.randbits(63)
    requested_players = _requested_player_configs(command, dependencies.config)
    setup = command.setup
    mechanics = setup.mechanics
    player_definitions = PlayerSetupDefinitions(
        players=PlayerRoster(
            players={
                character_id: PlayerProfile(
                    name=character.name,
                    age=character.age,
                    gender=character.gender,
                    personality=character.personality,
                    speaking_style=character.speaking_style,
                    reasoning_style=character.reasoning_style,
                    risk_tolerance=character.risk_tolerance,
                )
                for character_id, character in setup.roster.characters.items()
            }
        )
    )
    selected_profiles = _select_player_profiles(
        player_definitions.players,
        player_count=len(requested_players),
        seed=seed,
        character_assignments=setup.roster.assignments,
    )
    players = [
        {
            "id": player.id,
            "name": display_name_for(player.name, selected_profile),
        }
        for player, selected_profile in zip(requested_players, selected_profiles, strict=True)
    ]
    rule_composition = mechanics.composition.model_dump(mode="json")
    definition = rule_definition_from_values(
        player_count=len(players),
        role_counts=mechanics.role_counts,
        rules=mechanics.rules.model_dump(mode="json"),
        roles={role_id: role.model_dump(mode="json") for role_id, role in mechanics.roles.items()},
        abilities={
            ability_id: ability.model_dump(mode="json")
            for ability_id, ability in mechanics.abilities.items()
        },
        composition=rule_composition,
    )
    rules = RuleRegistry.standard().build(definition)
    setup_payload = setup.model_dump(mode="json")
    scenario_config = {
        "scenario_id": setup.theme.id,
        "scenario_name": setup.theme.name,
        "scenario_prompt_premise": setup.theme.premise,
        "setup_preset_id": "",
    }
    run_config = {
        **scenario_config,
        "narration_mode": command.narration_mode,
        "llm_mode": command.llm_mode,
        "engine_schema_version": setup.schema_version,
        "definition_snapshot": setup_payload,
        "setup_document": setup_payload,
        "setup_checksum": checksum_payload(setup_payload),
        "mechanics_checksum": checksum_payload(mechanics.model_dump(mode="json")),
        "rule_composition": rule_composition,
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
        game_setup_from_data({"players": players}),
        rules=rules,
        random=random.Random(seed),
    )
    snapshot = game.snapshot()
    events = list(game.creation_events)
    public_state = public_state_payload_from_snapshot(
        snapshot,
        game_id=str(game_id),
        version=1,
        seed=seed,
        scenario_id=_config_text(scenario_config, "scenario_id"),
        scenario_name=_config_text(scenario_config, "scenario_name"),
        narration_mode=command.narration_mode,
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
            narration_profile=_narration_profile(run_config, dependencies.game_definitions),
            narration_mode=command.narration_mode,
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

    game = _restore_game(run)
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
        rules=LocalRulesDefinition.model_validate(domain_to_data(snapshot.config.rules)),
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
                        seer_id=inspection.seer_id,
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
