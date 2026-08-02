"""1.0.0へ向けて維持する標準domain動作を固定する。"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Mapping, Sequence

import pytest

from werewolf_agent.domain import (
    AbilityDefinition,
    Action,
    DiscussionConfig,
    DiscussionPosition,
    DiscussionRelation,
    EventVisibility,
    Game,
    GameEvent,
    GameSetup,
    GameState,
    LifecycleConfig,
    NightConfig,
    Phase,
    Player,
    RoleCatalog,
    RoleDefinition,
    RuleSetDefinition,
    RuleViolation,
    VotingConfig,
    build_game_rules,
)


def _vote(game: Game, player_id: str, target_id: str) -> Action:
    """対象に関する公開発言またはpassを根拠に投票する。"""
    speech = next(
        (
            item
            for item in reversed(game.snapshot().history.speeches)
            if target_id in {item.player_id, item.topic_id}
        ),
        None,
    )
    if speech is not None:
        evidence_id = speech.speech_id
    else:
        result = next(
            item
            for item in reversed(game.snapshot().history.discussions)
            if target_id in item.passed_player_ids
        )
        evidence_id = f"pass:{result.day}:{result.round_id}:{target_id}"
    return Action.vote(player_id, target_id, reason="test", evidence_id=evidence_id)


def _active_ability(
    kind: str,
    *,
    enabled_first_night: bool = True,
) -> AbilityDefinition:
    return AbilityDefinition(
        kind=kind,
        phase=Phase.NIGHT,
        target_policy="other_alive_non_faction" if kind == "attack" else "other_alive",
        start_day=1,
        max_uses=None,
        result_visibility="private" if kind == "inspect" else "none",
        resolution_priority=100,
        allow_repeat_target=True,
        enabled_first_night=enabled_first_night,
        result_detail="faction" if kind == "inspect" else None,
        knowledge_mode=None,
        tie_resolution="no_action" if kind == "attack" else None,
        source_kinds=(),
    )


def _passive_ability(
    kind: str,
    *,
    phase: Phase,
    source_kinds: tuple[str, ...] = (),
) -> AbilityDefinition:
    return AbilityDefinition(
        kind=kind,
        phase=phase,
        target_policy="none",
        start_day=1,
        max_uses=1,
        result_visibility="none",
        resolution_priority=100,
        allow_repeat_target=True,
        enabled_first_night=True,
        result_detail=None,
        knowledge_mode=None,
        tie_resolution=None,
        source_kinds=source_kinds,
    )


def _knowledge_ability(
    mode: str,
    *,
    detail: str = "faction",
    visibility: str = "private",
) -> AbilityDefinition:
    return AbilityDefinition(
        kind="knowledge",
        phase=Phase.NIGHT,
        target_policy="none",
        start_day=1,
        max_uses=None,
        result_visibility=visibility,
        resolution_priority=100,
        allow_repeat_target=True,
        enabled_first_night=True,
        result_detail=detail,
        knowledge_mode=mode,
        tie_resolution=None,
        source_kinds=(),
    )


def _game(
    players: Sequence[Player],
    *,
    roles: Mapping[str, RoleDefinition],
    abilities: Mapping[str, AbilityDefinition] | None = None,
    starting_phase: str = "night",
    reveal_role_on_death: bool = False,
) -> Game:
    role_counts = Counter(player.role for player in players)
    assert None not in role_counts
    rules = build_game_rules(
        RuleSetDefinition(
            player_count=len(players),
            role_counts={str(role): count for role, count in role_counts.items()},
            discussion=DiscussionConfig(),
            voting=VotingConfig(),
            night=NightConfig(),
            lifecycle=LifecycleConfig(
                starting_phase=starting_phase,
                reveal_role_on_death=reveal_role_on_death,
                require_all_actions_before_advance=False,
            ),
            roles=RoleCatalog(roles),
            abilities=abilities or {},
        )
    )
    return Game.create(
        GameSetup(tuple(players)),
        rules=rules,
        random=random.Random(0),
    )


def _submit_and_advance(
    game: Game,
    actions: Sequence[Action],
    *,
    seed: int,
) -> tuple[GameEvent, ...]:
    events: list[GameEvent] = []
    for action in actions:
        events.extend(game.submit(action))
    events.extend(game.advance(random.Random(seed)))
    return tuple(events)


def _advance_to_voting(game: Game, *, seed: int = 0) -> None:
    """全議論stageを暗黙passで完了して投票へ進める。"""
    while game.snapshot().phase is Phase.DAY_DISCUSSION:
        game.advance(random.Random(seed))
        seed += 1


def test_first_night_inspection_is_private_and_does_not_require_disabled_actions() -> None:
    game = _game(
        (
            Player("p1", "Seer", "seer"),
            Player("p2", "Wolf", "werewolf"),
            Player("p3", "Villager A", "villager"),
            Player("p4", "Villager B", "villager"),
        ),
        roles={
            "seer": RoleDefinition("village", "village", ("inspect",)),
            "werewolf": RoleDefinition("werewolf", "werewolf", ("attack",)),
            "villager": RoleDefinition("village", "village"),
        },
        abilities={
            "inspect": _active_ability("inspect"),
            "attack": _active_ability("attack", enabled_first_night=False),
        },
    )

    submission = game.submit(Action.use_ability("p1", "inspect", "p2"))
    assert submission[0].visibility is EventVisibility.PLAYER_PRIVATE
    assert "target_id" not in submission[0].payload
    assert game.view_for("p2").available_actions == ()

    resolution = game.advance(random.Random(7))

    assert [event.event_type for event in resolution] == ["night_resolved", "phase_started"]
    assert "inspections" not in resolution[0].payload
    assert game.snapshot().history.nights[0].inspections[0].target_id == "p2"
    assert game.view_for("p1").known_factions["p2"] == "werewolf"
    assert "p2" not in game.view_for("p3").known_factions


def test_private_allies_knowledge_is_visible_only_to_ability_owner() -> None:
    game = _game(
        (
            Player("p1", "Wolf A", "werewolf"),
            Player("p2", "Wolf B", "werewolf"),
            Player("p3", "Villager A", "villager"),
            Player("p4", "Villager B", "villager"),
        ),
        roles={
            "werewolf": RoleDefinition("werewolf", "werewolf", ("allies",)),
            "villager": RoleDefinition("village", "village"),
        },
        abilities={"allies": _knowledge_ability("allies")},
    )

    assert game.view_for("p1").known_factions["p2"] == "werewolf"
    assert game.view_for("p2").known_factions["p1"] == "werewolf"
    assert "p1" not in game.view_for("p3").known_factions


def test_last_eliminated_knowledge_reveals_role_only_to_ability_owner() -> None:
    game = _game(
        (
            Player("p1", "Wolf", "werewolf"),
            Player("p2", "Medium", "medium"),
            Player("p3", "Villager A", "villager"),
            Player("p4", "Villager B", "villager"),
        ),
        roles={
            "werewolf": RoleDefinition("werewolf", "werewolf"),
            "medium": RoleDefinition("village", "village", ("medium",)),
            "villager": RoleDefinition("village", "village"),
        },
        abilities={
            "medium": _knowledge_ability("last_eliminated", detail="role"),
        },
        starting_phase="day_discussion",
    )
    _advance_to_voting(game)
    _submit_and_advance(
        game,
        (
            _vote(game, "p1", "p3"),
            _vote(game, "p2", "p3"),
            _vote(game, "p3", "p1"),
            _vote(game, "p4", "p3"),
        ),
        seed=19,
    )

    assert game.view_for("p2").known_roles["p3"] == "villager"
    assert "p3" not in game.view_for("p4").known_roles


def test_same_definition_seed_and_actions_reproduce_state_and_events() -> None:
    def run() -> tuple[GameState, tuple[GameEvent, ...]]:
        game = _game(
            (
                Player("p1", "Wolf", "werewolf"),
                Player("p2", "Villager A", "villager"),
                Player("p3", "Villager B", "villager"),
            ),
            roles={
                "werewolf": RoleDefinition("werewolf", "werewolf"),
                "villager": RoleDefinition("village", "village"),
            },
            starting_phase="day_discussion",
        )
        events = list(game.creation_events)
        events.extend(
            game.submit(
                Action.speech(
                    "p2",
                    "確認します。",
                    topic_id="p1",
                    position=DiscussionPosition.SUPPORT,
                    relation=DiscussionRelation.INDEPENDENT,
                )
            )
        )
        phase_seed = 11
        while game.snapshot().phase is Phase.DAY_DISCUSSION:
            events.extend(game.advance(random.Random(phase_seed)))
            phase_seed += 1
        for action in (
            _vote(game, "p1", "p2"),
            _vote(game, "p2", "p1"),
            _vote(game, "p3", "p1"),
        ):
            events.extend(game.submit(action))
        events.extend(game.advance(random.Random(13)))
        return game.snapshot(), tuple(events)

    first_state, first_events = run()
    second_state, second_events = run()

    assert first_state == second_state
    assert first_events == second_events
    assert first_state.phase is Phase.FINISHED
    assert first_state.winner_id == "village"
    assert any(event.event_type == "vote_resolved" for event in first_events)
    assert first_events[-1].event_type == "game_finished"


def test_rejected_action_preserves_state_and_pending_actions() -> None:
    game = _game(
        (
            Player("p1", "Wolf", "werewolf"),
            Player("p2", "Villager A", "villager"),
            Player("p3", "Villager B", "villager"),
        ),
        roles={
            "werewolf": RoleDefinition("werewolf", "werewolf"),
            "villager": RoleDefinition("village", "village"),
        },
        starting_phase="day_discussion",
    )
    game.submit(
        Action.speech(
            "p2",
            "一度だけ話します。",
            topic_id="p1",
            position=DiscussionPosition.SUPPORT,
            relation=DiscussionRelation.INDEPENDENT,
        )
    )
    before_state = game.snapshot()
    before_pending = game.pending_actions

    with pytest.raises(RuleViolation, match="not available"):
        game.submit(
            Action.speech(
                "p2",
                "二度目は拒否されます。",
                topic_id="p1",
                position=DiscussionPosition.SUPPORT,
                relation=DiscussionRelation.INDEPENDENT,
            )
        )

    assert game.snapshot() is before_state
    assert game.pending_actions is before_pending


def test_immunity_prevents_configured_attack_and_consumes_one_use() -> None:
    game = _game(
        (
            Player("p1", "Wolf", "werewolf"),
            Player("p2", "Immune", "immune"),
            Player("p3", "Villager A", "villager"),
            Player("p4", "Villager B", "villager"),
        ),
        roles={
            "werewolf": RoleDefinition("werewolf", "werewolf", ("attack",)),
            "immune": RoleDefinition("village", "village", ("immunity",)),
            "villager": RoleDefinition("village", "village"),
        },
        abilities={
            "attack": _active_ability("attack"),
            "immunity": _passive_ability(
                "immunity",
                phase=Phase.NIGHT,
                source_kinds=("attack",),
            ),
        },
    )

    resolution = _submit_and_advance(
        game,
        (Action.use_ability("p1", "attack", "p2"),),
        seed=17,
    )

    assert game.snapshot().players["p2"].is_alive
    assert game.snapshot().ability_uses["p2"]["immunity"] == 1
    assert (
        next(event for event in resolution if event.event_type == "night_resolved").payload[
            "killed_player_ids"
        ]
        == ()
    )


def test_vulnerability_turns_private_inspection_into_a_death() -> None:
    game = _game(
        (
            Player("p1", "Seer", "seer"),
            Player("p2", "Vulnerable", "vulnerable"),
            Player("p3", "Wolf", "werewolf"),
            Player("p4", "Villager", "villager"),
        ),
        roles={
            "seer": RoleDefinition("village", "village", ("inspect",)),
            "vulnerable": RoleDefinition("village", "village", ("vulnerability",)),
            "werewolf": RoleDefinition("werewolf", "werewolf"),
            "villager": RoleDefinition("village", "village"),
        },
        abilities={
            "inspect": _active_ability("inspect"),
            "vulnerability": _passive_ability(
                "vulnerability",
                phase=Phase.NIGHT,
                source_kinds=("inspect",),
            ),
        },
    )

    resolution = _submit_and_advance(
        game,
        (Action.use_ability("p1", "inspect", "p2"),),
        seed=19,
    )

    assert not game.snapshot().players["p2"].is_alive
    assert game.snapshot().ability_uses["p2"]["vulnerability"] == 1
    assert game.view_for("p1").known_factions["p2"] == "village"
    assert next(event for event in resolution if event.event_type == "night_resolved").payload[
        "killed_player_ids"
    ] == ("p2",)


def test_death_reaction_resolves_once_and_is_reported_without_hidden_ability_data() -> None:
    game = _game(
        (
            Player("p1", "Wolf", "werewolf"),
            Player("p2", "Hunter", "hunter"),
            Player("p3", "Villager A", "villager"),
            Player("p4", "Villager B", "villager"),
        ),
        roles={
            "werewolf": RoleDefinition("werewolf", "werewolf"),
            "hunter": RoleDefinition("village", "village", ("reaction",)),
            "villager": RoleDefinition("village", "village"),
        },
        abilities={
            "reaction": _passive_ability("death_reaction", phase=Phase.VOTING),
        },
        starting_phase="day_discussion",
    )
    _advance_to_voting(game)

    events = _submit_and_advance(
        game,
        (
            _vote(game, "p1", "p2"),
            _vote(game, "p2", "p1"),
            _vote(game, "p3", "p2"),
            _vote(game, "p4", "p2"),
        ),
        seed=23,
    )
    vote_event = next(event for event in events if event.event_type == "vote_resolved")
    reaction_ids = vote_event.payload["reaction_player_ids"]

    assert game.snapshot().players["p2"].eliminated_day == 1
    assert len(reaction_ids) == 1
    assert not game.snapshot().players[reaction_ids[0]].is_alive
    assert game.snapshot().ability_uses["p2"]["reaction"] == 1
    assert "ability_id" not in vote_event.payload
    assert "ability_uses" not in vote_event.payload


def test_living_fox_overrides_normal_village_victory() -> None:
    game = _game(
        (
            Player("p1", "Wolf", "werewolf"),
            Player("p2", "Fox", "fox"),
            Player("p3", "Villager A", "villager"),
            Player("p4", "Villager B", "villager"),
        ),
        roles={
            "werewolf": RoleDefinition("werewolf", "werewolf"),
            "fox": RoleDefinition("fox", "fox"),
            "villager": RoleDefinition("village", "village"),
        },
        starting_phase="day_discussion",
    )
    _advance_to_voting(game)

    _submit_and_advance(
        game,
        (
            _vote(game, "p1", "p3"),
            _vote(game, "p2", "p1"),
            _vote(game, "p3", "p1"),
            _vote(game, "p4", "p1"),
        ),
        seed=29,
    )

    assert game.snapshot().winner_id == "fox"
    assert game.snapshot().win_result is not None
    assert game.snapshot().win_result.winning_player_ids == ("p2",)
    visible_result = game.view_for("p3").win_result
    assert visible_result is not None
    assert visible_result.winner == "fox"
    assert not hasattr(visible_result, "winning_player_ids")


def test_sealed_opening_is_hidden_until_the_round_resolves() -> None:
    game = _game(
        (
            Player("p1", "Wolf", "werewolf"),
            Player("p2", "Villager A", "villager"),
            Player("p3", "Villager B", "villager"),
        ),
        roles={
            "werewolf": RoleDefinition("werewolf", "werewolf"),
            "villager": RoleDefinition("village", "village"),
        },
        starting_phase="day_discussion",
    )

    game.submit(
        Action.speech(
            "p2",
            "公開する発言です。",
            topic_id="p1",
            position=DiscussionPosition.SUPPORT,
            relation=DiscussionRelation.INDEPENDENT,
        )
    )

    assert game.view_for("p1").history.speeches == ()
    game.advance(random.Random(0))
    speech = game.view_for("p1").history.speeches[0]
    assert speech.utterance == "公開する発言です。"
    assert speech.round_kind.value == "opening"
