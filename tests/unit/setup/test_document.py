from __future__ import annotations

import random

import pytest

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.application.setup_options import validate_setup_document
from werewolf_agent.domain import (
    Action,
    ActionType,
    AvailableAction,
    Game,
    GameSetup,
    Phase,
    Player,
    build_game_rules,
)
from werewolf_agent.setup import (
    GameSetupDocument,
    checksum_payload,
    generate_players,
    namespace_seed,
    rule_definition_from_values,
)


def _standard() -> GameSetupDocument:
    return build_setup_catalog().require_document("standard_6")


def _rules(setup: GameSetupDocument):
    mechanics = setup.mechanics
    return build_game_rules(
        rule_definition_from_values(
            player_count=sum(mechanics.role_counts.values()),
            role_counts=mechanics.role_counts,
            discussion=mechanics.discussion.to_mapping(),
            voting=mechanics.voting.to_mapping(),
            night=mechanics.night.to_mapping(),
            lifecycle=mechanics.lifecycle.to_mapping(),
            roles={key: value.to_mapping() for key, value in mechanics.roles.items()},
            abilities={key: value.to_mapping() for key, value in mechanics.abilities.items()},
        )
    )


def test_packaged_templates_are_complete_executable_v2_documents() -> None:
    catalog = build_setup_catalog()

    for template_id in catalog.template_order:
        setup = catalog.require_document(template_id)
        rules = _rules(setup)

        assert setup.schema_version == "0.7.0"
        assert rules.config.player_count == sum(setup.mechanics.role_counts.values())
        assert set(setup.theme.role_names) == set(setup.mechanics.roles)
        assert set(setup.theme.ability_names) == set(setup.mechanics.abilities)
        assert len(setup.player_generation.identities) >= rules.config.player_count


def test_arbitrary_role_id_runs_through_ability_envelope() -> None:
    setup = _standard()
    payload = setup.to_mapping()
    role = payload["mechanics"]["roles"].pop("seer")
    count = payload["mechanics"]["role_counts"].pop("seer")
    payload["mechanics"]["roles"]["oracle_custom"] = role
    payload["mechanics"]["role_counts"]["oracle_custom"] = count
    for field in ("role_names", "role_objectives", "role_descriptions"):
        payload["theme"][field]["oracle_custom"] = payload["theme"][field].pop("seer")
    custom = GameSetupDocument.from_mapping(payload)
    players = generate_players(custom.player_generation, player_count=6, seed=41)
    game = Game.create(
        GameSetup(
            players=tuple(Player(id=item.player_id, name=item.profile.name) for item in players)
        ),
        rules=_rules(custom),
        random=random.Random(namespace_seed(41, "role_assignment")),
    )
    oracle = next(
        player for player in game.snapshot().players.values() if player.role == "oracle_custom"
    )

    action = next(item for item in game.view_for(oracle.id).available_actions if item.ability_id)

    assert action.type is ActionType.USE_ABILITY
    assert action.ability_id == "inspect"


def test_night_ability_can_be_explicitly_passed() -> None:
    payload = _standard().to_mapping()
    payload["mechanics"]["night"]["allow_pass"] = True
    setup = GameSetupDocument.from_mapping(payload)
    players = generate_players(setup.player_generation, player_count=6, seed=41)
    game = Game.create(
        GameSetup(
            players=tuple(Player(id=item.player_id, name=item.profile.name) for item in players)
        ),
        rules=_rules(setup),
        random=random.Random(namespace_seed(41, "role_assignment")),
    )
    actor = next(
        player
        for player in game.snapshot().players.values()
        if any(
            action.type is ActionType.USE_ABILITY
            for action in game.view_for(player.id).available_actions
        )
    )

    assert AvailableAction(ActionType.PASS) in game.view_for(actor.id).available_actions
    game.submit(Action.pass_(actor.id))
    assert game.pending_actions.night_actions[actor.id].type is ActionType.PASS


def test_structured_discussion_repeats_configured_cycles_with_default_one() -> None:
    payload = _standard().to_mapping()
    assert payload["mechanics"]["discussion"]["cycles_per_day"] == 1
    without_cycles = _standard().to_mapping()
    del without_cycles["mechanics"]["discussion"]["cycles_per_day"]
    assert GameSetupDocument.from_mapping(without_cycles).mechanics.discussion.cycles_per_day == 1
    payload["mechanics"]["discussion"]["cycles_per_day"] = 2
    payload["mechanics"]["lifecycle"]["starting_phase"] = "day_discussion"
    setup = GameSetupDocument.from_mapping(payload)
    players = generate_players(setup.player_generation, player_count=6, seed=31)
    game = Game.create(
        GameSetup(tuple(Player(item.player_id, item.profile.name) for item in players)),
        rules=_rules(setup),
        random=random.Random(namespace_seed(31, "role_assignment")),
    )

    first_round = game.snapshot().pending_actions.discussion_round
    assert first_round is not None
    for player_id in first_round.actor_order:
        topic_id = next(item for item in first_round.actor_order if item != player_id)
        game.submit(
            Action.speech(
                player_id,
                f"{player_id}の意見です。",
                topic_id=topic_id,
                position="undecided",
                relation="independent",
            )
        )
    game.advance(random.Random(1))

    response_round = game.snapshot().pending_actions.discussion_round
    assert response_round is not None
    assert response_round.kind.value == "response"
    assert len(response_round.reference_ids) == len(first_round.actor_order)
    for player_id in response_round.actor_order:
        game.submit(Action.pass_(player_id))
        game.advance(random.Random(2))

    second_round = game.snapshot().pending_actions.discussion_round
    assert second_round is not None
    assert second_round.cycle == 2
    assert second_round.kind.value == "opening"


def test_resolution_priority_controls_protection_order() -> None:
    setup = _standard()
    payload = setup.to_mapping()
    payload["mechanics"]["lifecycle"]["require_all_actions_before_advance"] = False

    def resolve(guard_priority: int) -> bool:
        configured = payload.copy()
        configured["mechanics"] = dict(payload["mechanics"])
        configured["mechanics"]["abilities"] = {
            key: dict(value) for key, value in payload["mechanics"]["abilities"].items()
        }
        configured["mechanics"]["abilities"]["guard"]["resolution_priority"] = guard_priority
        document = GameSetupDocument.from_mapping(configured)
        players = generate_players(document.player_generation, player_count=6, seed=13)
        game = Game.create(
            GameSetup(
                players=tuple(Player(id=item.player_id, name=item.profile.name) for item in players)
            ),
            rules=_rules(document),
            random=random.Random(namespace_seed(13, "role_assignment")),
        )
        by_role = {player.role: player.id for player in game.snapshot().players.values()}
        victim_id = next(
            player.id for player in game.snapshot().players.values() if player.role == "villager"
        )
        game.submit(Action.use_ability(by_role["knight"], "guard", victim_id))
        game.submit(Action.use_ability(by_role["werewolf"], "night_attack", victim_id))
        game.advance(random.Random(1))
        return game.snapshot().players[victim_id].is_alive

    assert resolve(50)
    assert not resolve(150)


def test_repeat_target_rule_applies_to_every_active_ability_kind() -> None:
    payload = _standard().to_mapping()
    payload["mechanics"]["abilities"]["inspect"]["allow_repeat_target"] = False
    payload["mechanics"]["lifecycle"]["require_all_actions_before_advance"] = False
    setup = GameSetupDocument.from_mapping(payload)
    players = generate_players(setup.player_generation, player_count=6, seed=29)
    game = Game.create(
        GameSetup(
            players=tuple(Player(id=item.player_id, name=item.profile.name) for item in players)
        ),
        rules=_rules(setup),
        random=random.Random(namespace_seed(29, "role_assignment")),
    )
    seer_id = next(
        player.id for player in game.snapshot().players.values() if player.role == "seer"
    )
    first_targets = game.view_for(seer_id).legal_targets["use_ability:inspect"]
    inspected_id = first_targets[0]
    game.submit(Action.use_ability(seer_id, "inspect", inspected_id))
    game.advance(random.Random(1))
    game.advance(random.Random(2))
    game.advance(random.Random(3))

    assert inspected_id not in game.view_for(seer_id).legal_targets["use_ability:inspect"]


def test_packaged_setup_reaches_a_winner_deterministically() -> None:
    setup = _standard()
    players = generate_players(setup.player_generation, player_count=6, seed=7)
    game = Game.create(
        GameSetup(
            players=tuple(Player(id=item.player_id, name=item.profile.name) for item in players)
        ),
        rules=_rules(setup),
        random=random.Random(namespace_seed(7, "role_assignment")),
    )
    gameplay = random.Random(namespace_seed(7, "gameplay"))
    for _ in range(64):
        if game.snapshot().phase is Phase.FINISHED:
            break
        for player in tuple(game.snapshot().players.values()):
            view = game.view_for(player.id)
            while view.available_actions:
                available = view.available_actions[0]
                targets = view.legal_targets.get(available.key, ())
                if available.type is ActionType.SPEECH:
                    round_ = view.discussion_round
                    speeches = {speech.speech_id: speech for speech in view.history.speeches}
                    reference_id = (
                        next(
                            reference_id
                            for reference_id in round_.reference_ids
                            if speeches[reference_id].player_id != player.id
                        )
                        if round_ is not None and round_.reference_ids
                        else None
                    )
                    topic_id = next(
                        item.id for item in view.players if item.id != player.id and item.is_alive
                    )
                    action = Action.speech(
                        player.id,
                        "その発言には異論があります。" if reference_id else "状況を確認します。",
                        topic_id=(speeches[reference_id].topic_id if reference_id else topic_id),
                        position=(
                            "oppose"
                            if reference_id and speeches[reference_id].position.value == "support"
                            else "support"
                        ),
                        relation="challenge" if reference_id else "independent",
                        evidence_id=reference_id,
                        response_to_id=reference_id,
                    )
                elif available.type is ActionType.VOTE:
                    evidence_id = next(
                        speech.speech_id
                        for speech in reversed(view.history.speeches)
                        if targets[0] in {speech.player_id, speech.topic_id}
                    )
                    action = Action.vote(
                        player.id,
                        targets[0],
                        reason="状況から判断します。",
                        evidence_id=evidence_id,
                    )
                elif available.type is ActionType.USE_ABILITY:
                    action = Action.use_ability(
                        player.id,
                        available.ability_id or "",
                        targets[0],
                    )
                else:
                    action = Action.pass_(player.id)
                game.submit(action)
                view = game.view_for(player.id)
        game.advance(gameplay)

    assert game.snapshot().phase is Phase.FINISHED
    assert game.snapshot().winner_id in {"village", "werewolf", "fox"}


def test_player_generation_is_reproducible_and_preview_safe() -> None:
    setup = _standard()
    first = generate_players(setup.player_generation, player_count=6, seed=99)
    second = generate_players(setup.player_generation, player_count=6, seed=99)

    assert first == second
    assert [item.player_id for item in first] == [f"p{index}" for index in range(1, 7)]
    assert len({item.profile.name for item in first}) == 6
    assert all("reasoning_style" not in item.public_payload() for item in first)
    assert namespace_seed(99, "roster") != namespace_seed(99, "role_assignment")
    assert namespace_seed(99, "role_assignment") != namespace_seed(99, "gameplay")


def test_setup_rejects_missing_theme_coverage_and_kind_specific_extras() -> None:
    payload = _standard().to_mapping()
    del payload["theme"]["role_objectives"]["werewolf"]
    with pytest.raises(ValueError, match="theme coverage"):
        GameSetupDocument.from_mapping(payload)

    payload = _standard().to_mapping()
    payload["mechanics"]["abilities"]["guard"]["result_detail"] = "role"
    with pytest.raises(ValueError, match="extra"):
        GameSetupDocument.from_mapping(payload)


def test_setup_rejects_blank_generation_and_enabled_empty_narration() -> None:
    payload = _standard().to_mapping()
    payload["player_generation"]["public_personas"][0]["personality"] = "  "
    with pytest.raises(ValueError, match="personality must not be blank"):
        GameSetupDocument.from_mapping(payload)

    payload = _standard().to_mapping()
    payload["theme"]["narration_enabled"] = True
    payload["theme"]["narration"] = {}
    with pytest.raises(ValueError, match="enabled narration"):
        GameSetupDocument.from_mapping(payload)

    payload = _standard().to_mapping()
    del payload["theme"]["narration"]["game_finished"]
    with pytest.raises(ValueError, match="cover every supported event"):
        GameSetupDocument.from_mapping(payload)

    payload = _standard().to_mapping()
    payload["theme"]["narration"]["game_started"] = ["秘密: {private_role}"]
    with pytest.raises(ValueError, match="unknown fields"):
        GameSetupDocument.from_mapping(payload)

    payload = _standard().to_mapping()
    payload["theme"]["narration"]["game_started"] = ["{player_count:1000000}"]
    with pytest.raises(ValueError, match="invalid format syntax"):
        GameSetupDocument.from_mapping(payload)

    payload = _standard().to_mapping()
    payload["theme"]["narration"]["game_started"] = ["{player_count!r}"]
    with pytest.raises(ValueError, match="invalid format syntax"):
        GameSetupDocument.from_mapping(payload)


def test_behavioral_ability_fields_are_explicit() -> None:
    payload = _standard().to_mapping()
    del payload["mechanics"]["abilities"]["inspect"]["max_uses"]

    with pytest.raises(ValueError, match="max_uses"):
        GameSetupDocument.from_mapping(payload)

    payload = _standard().to_mapping()
    payload["mechanics"]["role_counts"]["villager"] = 0
    with pytest.raises(ValueError, match="role count"):
        GameSetupDocument.from_mapping(payload)


@pytest.mark.parametrize(
    ("kind", "phase", "source_kinds"),
    [
        ("immunity", "voting", ["attack"]),
        ("immunity", "night", ["protect"]),
        ("vulnerability", "night", []),
        ("vulnerability", "night", ["attack"]),
        ("death_reaction", "day_discussion", None),
    ],
)
def test_setup_rejects_passive_combinations_without_runtime_meaning(
    kind: str,
    phase: str,
    source_kinds: list[str] | None,
) -> None:
    payload = _standard().to_mapping()
    ability: dict[str, object] = {
        "kind": kind,
        "phase": phase,
        "target_policy": "none",
        "start_day": 1,
        "max_uses": "unlimited",
        "result_visibility": "none",
        "resolution_priority": 100,
        "allow_repeat_target": True,
        "enabled_first_night": True,
    }
    if source_kinds is not None:
        ability["source_kinds"] = source_kinds
    payload["mechanics"]["abilities"]["custom_passive"] = ability
    payload["mechanics"]["roles"]["villager"]["abilities"].append("custom_passive")
    payload["theme"]["ability_names"]["custom_passive"] = "追加能力"
    payload["theme"]["ability_descriptions"]["custom_passive"] = "追加した能力です。"

    with pytest.raises(ValueError):
        GameSetupDocument.from_mapping(payload)


def test_setup_validation_returns_canonical_checksums() -> None:
    setup = _standard()

    result = validate_setup_document(setup.to_mapping())

    assert result.player_count == 6
    assert result.setup_checksum == checksum_payload(setup.to_mapping())
    assert result.mechanics_checksum == checksum_payload(setup.mechanics.to_mapping())
