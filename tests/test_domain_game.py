import random

import pytest
from pydantic import ValidationError

from werewolf_agent.commons import GameError, GamePhaseError
from werewolf_agent.domain.models import (
    DomainEvent,
    Faction,
    Game,
    GameConfig,
    KnightGuardAction,
    Phase,
    PlayerConfig,
    PlayerStatus,
    Role,
    SeerInspectAction,
    SpeechAction,
    TieBreakPolicy,
    VoteAction,
    WerewolfAttackAction,
)


class ListEventSink:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def write(self, event: DomainEvent) -> None:
        self.events.append(event)


def mvp_config(*, tie_break_policy: TieBreakPolicy = TieBreakPolicy.NO_ELIMINATION) -> GameConfig:
    return GameConfig(
        game_id="game-1",
        player_count=5,
        role_counts={
            Role.WEREWOLF: 1,
            Role.SEER: 1,
            Role.KNIGHT: 1,
            Role.VILLAGER: 2,
        },
        seed=7,
        tie_break_policy=tie_break_policy,
    )


def fixed_players() -> list[PlayerConfig]:
    return [
        PlayerConfig(player_id="p1", name="Alice", role=Role.WEREWOLF),
        PlayerConfig(player_id="p2", name="Bob", role=Role.SEER),
        PlayerConfig(player_id="p3", name="Chika", role=Role.KNIGHT),
        PlayerConfig(player_id="p4", name="Dan", role=Role.VILLAGER),
        PlayerConfig(player_id="p5", name="Eve", role=Role.VILLAGER),
    ]


def start_fixed_game(
    *,
    tie_break_policy: TieBreakPolicy = TieBreakPolicy.NO_ELIMINATION,
    event_sink: ListEventSink | None = None,
) -> Game:
    return Game.start(
        config=mvp_config(tie_break_policy=tie_break_policy),
        players=fixed_players(),
        rng=random.Random(7),
        event_sink=event_sink,
    )


def advance_to_voting(game: Game) -> None:
    game.advance_phase()
    game.advance_phase()
    assert game.phase is Phase.VOTING


def test_game_config_validates_role_counts() -> None:
    with pytest.raises(ValidationError):
        GameConfig(
            player_count=5,
            role_counts={Role.WEREWOLF: 1, Role.VILLAGER: 3},
        )


def test_game_start_is_headless_and_emits_injected_events() -> None:
    sink = ListEventSink()
    game = start_fixed_game(event_sink=sink)

    snapshot = game.snapshot()

    assert snapshot.phase is Phase.NIGHT
    assert snapshot.day == 1
    assert snapshot.players["p1"].role is Role.WEREWOLF
    assert sink.events[0].event_type == "game_started"
    assert sink.events[0].payload["role_counts"] == {
        "werewolf": 1,
        "seer": 1,
        "knight": 1,
        "villager": 2,
    }


def test_observation_hides_secret_roles_but_shows_allowed_knowledge() -> None:
    game = start_fixed_game()

    seer_observation = game.observation_for("p2")
    wolf_observation = game.observation_for("p1")

    assert seer_observation.known_roles == {"p2": Role.SEER}
    assert {player.player_id: player.role for player in seer_observation.players} == {
        "p1": None,
        "p2": Role.SEER,
        "p3": None,
        "p4": None,
        "p5": None,
    }
    assert wolf_observation.known_roles == {"p1": Role.WEREWOLF}


def test_night_actions_resolve_guard_and_private_seer_knowledge() -> None:
    game = start_fixed_game()

    game.submit_night_action(WerewolfAttackAction(player_id="p1", target_id="p4"))
    game.submit_night_action(SeerInspectAction(player_id="p2", target_id="p1"))
    game.submit_night_action(KnightGuardAction(player_id="p3", target_id="p4"))
    snapshot = game.advance_phase()

    assert snapshot.phase is Phase.DAY_DISCUSSION
    assert snapshot.players["p4"].status is PlayerStatus.ALIVE
    assert snapshot.night_history[-1].protected_player_id == "p4"
    assert snapshot.night_history[-1].killed_player_id is None
    assert game.observation_for("p2").known_roles["p1"] is Role.WEREWOLF
    assert "p1" not in game.observation_for("p4").known_roles


def test_vote_resolution_eliminates_player_and_finishes_game() -> None:
    game = start_fixed_game()
    advance_to_voting(game)

    for voter_id in ["p2", "p3", "p4", "p5"]:
        game.submit_vote(VoteAction(player_id=voter_id, target_id="p1"))
    game.submit_vote(VoteAction(player_id="p1", target_id="p5"))
    snapshot = game.advance_phase()

    assert snapshot.phase is Phase.FINISHED
    assert snapshot.players["p1"].status is PlayerStatus.DEAD
    assert snapshot.vote_history[-1].eliminated_player_id == "p1"
    assert snapshot.win_result is not None
    assert snapshot.win_result.winner is Faction.VILLAGE


def test_vote_tie_policy_can_leave_everyone_alive() -> None:
    game = start_fixed_game()
    advance_to_voting(game)

    game.submit_vote(VoteAction(player_id="p1", target_id="p4"))
    game.submit_vote(VoteAction(player_id="p2", target_id="p4"))
    game.submit_vote(VoteAction(player_id="p3", target_id="p5"))
    game.submit_vote(VoteAction(player_id="p4", target_id="p5"))
    snapshot = game.advance_phase()

    assert snapshot.phase is Phase.NIGHT
    assert snapshot.day == 2
    assert snapshot.vote_history[-1].eliminated_player_id is None
    assert snapshot.vote_history[-1].tied_player_ids == ["p4", "p5"]
    assert snapshot.vote_history[-1].missing_voter_ids == ["p5"]


def test_invalid_actions_raise_safe_game_errors() -> None:
    game = start_fixed_game()

    with pytest.raises(GamePhaseError):
        game.submit_vote(VoteAction(player_id="p1", target_id="p2"))

    with pytest.raises(GameError):
        game.submit_night_action(SeerInspectAction(player_id="p4", target_id="p1"))


def test_day_speech_is_only_recorded_during_discussion() -> None:
    game = start_fixed_game()

    with pytest.raises(GamePhaseError):
        game.submit_day_action(SpeechAction(player_id="p2", message="too early"))

    game.advance_phase()
    game.submit_day_action(SpeechAction(player_id="p2", message="I have a read."))

    assert game.snapshot().speeches[-1].message == "I have a read."
