import random

import pytest
from pydantic import ValidationError

from werewolf_agent.adapters.application_bridge import (
    build_game_definitions,
    build_player_setup_definitions,
)
from werewolf_agent.application.replay import checksum_payload
from werewolf_agent.application.rules import rule_definition_from_values
from werewolf_agent.application.setup_document import setup_document_from_preset
from werewolf_agent.application.setup_options import validate_setup_document
from werewolf_agent.domain import Action, Game, GameSetup, Phase, Player, RuleRegistry
from werewolf_agent.settings import AppSettings


def _definitions():
    settings = AppSettings(_env_file=None)
    return build_game_definitions(settings), build_player_setup_definitions(settings)


def test_every_packaged_preset_resolves_to_executable_complete_setup() -> None:
    definitions, players = _definitions()

    for preset_id in definitions.catalog.setup_presets:
        setup = setup_document_from_preset(preset_id, definitions, players)
        mechanics = setup.mechanics
        definition = rule_definition_from_values(
            player_count=sum(mechanics.role_counts.values()),
            role_counts=mechanics.role_counts,
            rules=mechanics.rules.model_dump(mode="json"),
            roles={
                role_id: role.model_dump(mode="json") for role_id, role in mechanics.roles.items()
            },
            abilities={
                ability_id: ability.model_dump(mode="json")
                for ability_id, ability in mechanics.abilities.items()
            },
            composition=mechanics.composition.model_dump(mode="json"),
        )

        rules = RuleRegistry.standard().build(definition)

        assert rules.config.player_count == sum(mechanics.role_counts.values())
        assert setup.theme.role_names.keys() >= {
            role_id for role_id, count in mechanics.role_counts.items() if count > 0
        }
        assert setup.theme.role_objectives.keys() >= {
            role_id for role_id, count in mechanics.role_counts.items() if count > 0
        }


def test_every_packaged_preset_reaches_a_winner_for_multiple_seeds() -> None:
    definitions, player_definitions = _definitions()

    for preset_id in definitions.catalog.setup_presets:
        setup = setup_document_from_preset(preset_id, definitions, player_definitions)
        mechanics = setup.mechanics
        definition = rule_definition_from_values(
            player_count=sum(mechanics.role_counts.values()),
            role_counts=mechanics.role_counts,
            rules=mechanics.rules.model_dump(mode="json"),
            roles={
                role_id: role.model_dump(mode="json") for role_id, role in mechanics.roles.items()
            },
            abilities={
                ability_id: ability.model_dump(mode="json")
                for ability_id, ability in mechanics.abilities.items()
            },
            composition=mechanics.composition.model_dump(mode="json"),
        )
        rules = RuleRegistry.standard().build(definition)
        player_count = sum(mechanics.role_counts.values())

        for seed in range(3):
            game = Game.create(
                GameSetup(
                    players=tuple(
                        Player(id=f"player-{index}", name=f"Player {index}")
                        for index in range(1, player_count + 1)
                    )
                ),
                rules=rules,
                random=random.Random(seed),
            )
            for step in range(100):
                if game.snapshot().phase is Phase.FINISHED:
                    break
                for player in tuple(game.snapshot().players.values()):
                    view = game.view_for(player.id)
                    while view.available_actions:
                        action_type = view.available_actions[0]
                        targets = view.legal_targets.get(action_type, ())
                        game.submit(
                            Action(
                                type=action_type,
                                player_id=player.id,
                                target_id=targets[0] if targets else None,
                                message="状況を確認します。"
                                if action_type.value == "speech"
                                else None,
                            )
                        )
                        view = game.view_for(player.id)
                game.advance(random.Random(seed * 1000 + step))

            snapshot = game.snapshot()
            assert snapshot.phase is Phase.FINISHED, (preset_id, seed, snapshot.phase)
            assert snapshot.winner_id in {"village", "werewolf", "fox"}


def test_theme_changes_language_without_changing_mechanics_checksum() -> None:
    definitions, players = _definitions()
    village = setup_document_from_preset("standard_6", definitions, players)
    starship = village.model_copy(
        update={
            "theme": setup_document_from_preset("fox_8", definitions, players).theme,
        }
    )

    assert village.theme.role_names["werewolf"] == "人狼"
    assert starship.theme.role_names["werewolf"] == "擬態生命体"
    assert "人狼" not in starship.theme.role_objectives["werewolf"]
    assert starship.theme.ability_names["night_attack"] == "船内排除"
    assert checksum_payload(village.mechanics.model_dump(mode="json")) == checksum_payload(
        starship.mechanics.model_dump(mode="json")
    )
    assert checksum_payload(village.model_dump(mode="json")) != checksum_payload(
        starship.model_dump(mode="json")
    )


def test_preset_snapshot_contains_only_selected_mechanics_and_terms() -> None:
    definitions, players = _definitions()
    setup = setup_document_from_preset("beginner_6", definitions, players)

    assert set(setup.mechanics.roles) == {"villager", "werewolf", "seer"}
    assert set(setup.mechanics.abilities) == {"night_attack", "pack_knowledge", "inspect"}
    assert set(setup.theme.role_names) == set(setup.mechanics.roles)
    assert set(setup.theme.role_objectives) == set(setup.mechanics.roles)
    assert set(setup.theme.ability_names) == set(setup.mechanics.abilities)
    assert "fox" not in setup.theme.faction_names


def test_packaged_roles_separate_identity_from_victory_team() -> None:
    definitions, _players = _definitions()

    madman = definitions.roles.roles["madman"]
    fox = definitions.roles.roles["fox"]

    assert (madman.identity_faction, madman.victory_team) == ("village", "werewolf")
    assert (fox.identity_faction, fox.victory_team) == ("fox", "fox")


def test_setup_rejects_a_theme_without_a_selected_role_objective() -> None:
    definitions, players = _definitions()
    setup = setup_document_from_preset("standard_6", definitions, players)
    payload = setup.model_dump(mode="json")
    del payload["theme"]["role_objectives"]["werewolf"]

    with pytest.raises(ValidationError, match="role_objectives"):
        type(setup).model_validate(payload)


def test_setup_validation_returns_canonical_checksums_without_creating_a_game() -> None:
    definitions, players = _definitions()
    setup = setup_document_from_preset("standard_6", definitions, players)

    result = validate_setup_document(setup.model_dump(mode="json"))

    assert result.player_count == 6
    assert result.theme_id == "classic_village"
    assert set(result.role_ids) == set(setup.mechanics.roles)
    assert result.setup_checksum == checksum_payload(setup.model_dump(mode="json"))
    assert result.mechanics_checksum == checksum_payload(setup.mechanics.model_dump(mode="json"))
