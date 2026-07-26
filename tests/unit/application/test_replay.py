from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from typing import Any

from tests.unit.domain.test_domain_game import fixed_players, mvp_config, rule_set_for

from werewolf_agent.application.definitions import CustomCharacterDefinition
from werewolf_agent.application.domain_codec import domain_to_data
from werewolf_agent.application.projections import (
    event_to_create,
    public_state_payload_from_snapshot,
)
from werewolf_agent.application.randomness import runtime_seed
from werewolf_agent.application.replay import checksum_payload, verify_replay
from werewolf_agent.application.setup_document import (
    GameSetupDocument,
    MechanicsDefinition,
    RosterDefinition,
    StoryThemeDefinition,
)
from werewolf_agent.domain import Game, GameSetup, GameState
from werewolf_agent.domain.state import Action, Player


class _ReplayRepository:
    def __init__(self, records: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
        self._records = records

    def replay_records(self, _game_id: str) -> Mapping[str, Sequence[Mapping[str, Any]]]:
        return self._records


def _record(version: int, payload: object) -> dict[str, Any]:
    return {
        "version": version,
        "payload": payload,
        "checksum": checksum_payload(payload),
    }


def _setup_document(snapshot: GameState) -> GameSetupDocument:
    config = snapshot.config
    roles = {
        role_id: {
            **domain_to_data(role),
            "objective": "Meet the configured victory condition.",
            "label": role_id,
            "difficulty": 1,
        }
        for role_id, role in config.roles.roles.items()
    }
    abilities = {
        ability_id: {
            **domain_to_data(ability),
            "label": ability_id,
            "description": ability_id,
            "difficulty": 1,
        }
        for ability_id, ability in config.abilities.items()
    }
    mechanics = MechanicsDefinition.model_validate(
        {
            "role_counts": config.role_counts,
            "roles": roles,
            "abilities": abilities,
            "rules": domain_to_data(config.rules),
        }
    )
    action_ids = {ability.action.value for ability in config.abilities.values()} | {
        "speech",
        "vote",
        "pass",
    }
    theme = StoryThemeDefinition(
        id="test",
        name="Test",
        summary="Test setup",
        premise="A deterministic test game.",
        role_names={role_id: role_id for role_id in roles},
        role_objectives={role_id: str(role["objective"]) for role_id, role in roles.items()},
        faction_names={"village": "Village", "werewolf": "Werewolf"},
        ability_names={ability_id: ability_id for ability_id in abilities},
        action_names={action_id: action_id for action_id in action_ids},
        phase_names={
            "night": "Night",
            "day_discussion": "Discussion",
            "voting": "Voting",
            "finished": "Finished",
        },
    )
    characters = {
        player.id: CustomCharacterDefinition(
            id=player.id,
            name=player.name,
            age=20,
            gender="unspecified",
            personality="steady",
            speaking_style="brief",
            reasoning_style="logical",
            risk_tolerance="medium",
        )
        for player in snapshot.players.values()
    }
    return GameSetupDocument(
        mechanics=mechanics,
        theme=theme,
        roster=RosterDefinition(characters=characters),
    )


def test_replay_rejects_a_missing_state_version_even_when_checksums_match() -> None:
    repository = _ReplayRepository(
        {
            "commands": [_record(1, {}), _record(3, {})],
            "events": [],
            "states": [_record(1, {}), _record(3, {})],
        }
    )

    result = verify_replay("game-1", repository)

    assert result.valid is False
    assert result.first_mismatch_version == 2


def test_replay_rejects_a_missing_event_sequence() -> None:
    event_one = {**_record(1, {}), "sequence": 1}
    event_three = {**_record(1, {}), "sequence": 3}
    repository = _ReplayRepository(
        {
            "commands": [_record(1, {})],
            "events": [event_one, event_three],
            "states": [_record(1, {})],
        }
    )

    result = verify_replay("game-1", repository)

    assert result.valid is False
    assert result.first_mismatch_version == 1


def test_replay_rejects_a_state_event_that_differs_from_the_snapshot() -> None:
    state = _record(1, {"version": 1, "private_state": {}, "public_state": {}})
    state_event = {
        **_record(1, {"version": 1, "private_state": {"changed": True}, "public_state": {}}),
        "sequence": 1,
        "event_type": "state_committed",
    }
    repository = _ReplayRepository(
        {
            "commands": [_record(1, {})],
            "events": [state_event],
            "states": [state],
        }
    )

    result = verify_replay("game-1", repository)

    assert result.valid is False
    assert result.first_mismatch_version == 1


def test_replay_reexecutes_the_genesis_command() -> None:
    seed = 7
    setup_players = tuple(Player(id=player.id, name=player.name) for player in fixed_players())
    game = Game.create(
        GameSetup(players=setup_players),
        rules=rule_set_for(mvp_config()),
        random=random.Random(seed),
    )
    snapshot = game.snapshot()
    public_state = public_state_payload_from_snapshot(
        snapshot,
        game_id="game-1",
        version=1,
        seed=seed,
    )
    state_payload = {
        "version": 1,
        "private_state": domain_to_data(snapshot),
        "public_state": public_state,
    }
    command_payload = {
        "operation_type": "create_game",
        "actor_user_id": "user-1",
        "expected_version": None,
        "player_id": None,
        "request": {"seed": seed},
        "domain_actions": [],
        "replay": {
            "format_version": 2,
            "seed": seed,
            "setup_document": _setup_document(snapshot).model_dump(mode="json"),
            "setup_checksum": checksum_payload(_setup_document(snapshot).model_dump(mode="json")),
            "mechanics_checksum": checksum_payload(
                _setup_document(snapshot).mechanics.model_dump(mode="json")
            ),
            "players": [{"id": player.id, "name": player.name} for player in setup_players],
        },
    }
    created_event = event_to_create(game.creation_events[0], narration_mode="none")
    state_event = {
        **_record(1, state_payload),
        "sequence": 1,
        "event_type": "state_committed",
        "visibility": "private",
        "phase": snapshot.phase.value,
        "day": snapshot.day,
        "actor_id": None,
    }
    game_started = {
        **_record(1, created_event.payload),
        "sequence": 2,
        "event_type": created_event.event_type,
        "visibility": created_event.visibility,
        "phase": created_event.phase,
        "day": created_event.day,
        "actor_id": created_event.actor_id,
    }
    create_command = {
        **_record(1, command_payload),
        "command_type": "create_game",
        "actor_user_id": "user-1",
    }
    repository = _ReplayRepository(
        {
            "commands": [create_command],
            "events": [state_event, game_started],
            "states": [_record(1, state_payload)],
        }
    )

    result = verify_replay("game-1", repository)

    assert result.valid is True
    assert result.first_mismatch_version is None

    command_payload.pop("replay")
    create_command.update(_record(1, command_payload))

    unsupported = verify_replay("game-1", repository)

    assert unsupported.valid is False
    assert unsupported.first_mismatch_version == 1
    assert unsupported.comparison_target == "structure"

    create_command.pop("version")
    malformed = verify_replay("game-1", repository)

    assert malformed.valid is False
    assert malformed.first_mismatch_version == 1
    assert malformed.comparison_target == "structure"


def test_replay_reexecutes_player_action_and_advance_commands() -> None:
    seed = 11
    setup_players = tuple(Player(id=player.id, name=player.name) for player in fixed_players())
    game = Game.create(
        GameSetup(players=setup_players),
        rules=rule_set_for(mvp_config()),
        random=random.Random(seed),
    )
    first_snapshot = game.snapshot()
    actor_id = next(
        player.id
        for player in first_snapshot.players.values()
        if game.view_for(player.id).available_actions
    )
    view = game.view_for(actor_id)
    action_type = view.available_actions[0]
    target_id = view.legal_targets[action_type][0]
    action = Action(type=action_type, player_id=actor_id, target_id=target_id)
    action_events = game.submit(action)
    second_snapshot = game.snapshot()
    domain_actions: list[dict[str, Any]] = []
    advance_events = []
    for player in second_snapshot.players.values():
        view = game.view_for(player.id)
        while view.available_actions:
            automatic_type = view.available_actions[0]
            targets = view.legal_targets.get(automatic_type, ())
            automatic_action = Action(
                type=automatic_type,
                player_id=player.id,
                target_id=targets[0] if targets else None,
            )
            domain_actions.append(domain_to_data(automatic_action))
            advance_events.extend(game.submit(automatic_action))
            view = game.view_for(player.id)
    advance_events.extend(game.advance(random.Random(runtime_seed(seed, 2))))
    third_snapshot = game.snapshot()

    def state_payload(snapshot: GameState, version: int) -> dict[str, Any]:
        return {
            "version": version,
            "private_state": domain_to_data(snapshot),
            "public_state": public_state_payload_from_snapshot(
                snapshot,
                game_id="game-1",
                version=version,
                seed=seed,
            ),
        }

    first_state = state_payload(first_snapshot, 1)
    second_state = state_payload(second_snapshot, 2)
    third_state = state_payload(third_snapshot, 3)
    setup_document = _setup_document(first_snapshot)
    create_payload = {
        "operation_type": "create_game",
        "actor_user_id": "user-1",
        "expected_version": None,
        "player_id": None,
        "request": {"seed": seed},
        "domain_actions": [],
        "replay": {
            "format_version": 2,
            "seed": seed,
            "setup_document": setup_document.model_dump(mode="json"),
            "setup_checksum": checksum_payload(setup_document.model_dump(mode="json")),
            "mechanics_checksum": checksum_payload(
                setup_document.mechanics.model_dump(mode="json")
            ),
            "players": [{"id": player.id, "name": player.name} for player in setup_players],
        },
    }
    action_payload = {
        "operation_type": "submit_action",
        "actor_user_id": "user-1",
        "expected_version": 1,
        "player_id": actor_id,
        "request": domain_to_data(action),
        "domain_actions": [],
    }
    advance_payload = {
        "operation_type": "advance_game",
        "actor_user_id": "user-1",
        "expected_version": 2,
        "player_id": None,
        "request": {},
        "domain_actions": domain_actions,
    }
    events: list[dict[str, Any]] = []
    sequence = 0
    for version, state, generated in (
        (1, first_state, game.creation_events),
        (2, second_state, action_events),
        (3, third_state, advance_events),
    ):
        sequence += 1
        events.append(
            {
                **_record(version, state),
                "sequence": sequence,
                "event_type": "state_committed",
                "visibility": "private",
                "phase": state["private_state"]["phase"],
                "day": state["private_state"]["day"],
                "actor_id": None,
            }
        )
        for event in generated:
            sequence += 1
            created = event_to_create(event, narration_mode="none")
            events.append(
                {
                    **_record(version, created.payload),
                    "sequence": sequence,
                    "event_type": created.event_type,
                    "visibility": created.visibility,
                    "phase": created.phase,
                    "day": created.day,
                    "actor_id": created.actor_id,
                }
            )
    repository = _ReplayRepository(
        {
            "commands": [
                {
                    **_record(1, create_payload),
                    "command_type": "create_game",
                    "actor_user_id": "user-1",
                },
                {
                    **_record(2, action_payload),
                    "command_type": "submit_action",
                    "actor_user_id": "user-1",
                },
                {
                    **_record(3, advance_payload),
                    "command_type": "advance_game",
                    "actor_user_id": "user-1",
                },
            ],
            "events": events,
            "states": [
                _record(1, first_state),
                _record(2, second_state),
                _record(3, third_state),
            ],
        }
    )

    result = verify_replay("game-1", repository)

    assert result.valid is True
    assert result.checked_versions == 3

    commands = repository._records["commands"]
    assert isinstance(commands, list)
    second_command = commands[1]
    assert isinstance(second_command, dict)
    second_command["actor_user_id"] = "attacker"

    tampered = verify_replay("game-1", repository)

    assert tampered.valid is False
    assert tampered.first_mismatch_version == 2
    assert tampered.comparison_target == "command_metadata"
