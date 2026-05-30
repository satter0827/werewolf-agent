import random
from dataclasses import dataclass, field

import pytest
from pydantic import ValidationError

from werewolf_agent.contracts import GameError
from werewolf_agent.domain.game.models import (
    ABILITY_GUARD,
    ABILITY_INSPECT,
    ABILITY_NIGHT_ATTACK,
    ABILITY_PACK_KNOWLEDGE,
    FACTION_VILLAGE,
    FACTION_WEREWOLF,
    Action,
    ActionType,
    DomainEvent,
    GameConfig,
    GameSnapshot,
    LocalRules,
    PendingActions,
    Phase,
    Player,
    PlayerStatus,
    RoleCatalog,
    RoleDefinition,
)
from werewolf_agent.domain.game.service import advance_phase, observe, start_game, submit_action

ROLE_PLAIN = "plain"
ROLE_SHADOW = "shadow"
ROLE_READER = "reader"
ROLE_SHIELD = "shield"


@dataclass
class HeadlessRun:
    snapshot: GameSnapshot
    pending: PendingActions
    rng: random.Random
    events: list[DomainEvent] = field(default_factory=list)

    def observe(self, player_id: str):
        return observe(self.snapshot, self.pending, player_id)

    def submit(self, action: Action) -> None:
        self.snapshot, self.pending, events = submit_action(
            self.snapshot,
            self.pending,
            action,
        )
        self.events.extend(events)

    def advance(self) -> GameSnapshot:
        self.snapshot, self.pending, events = advance_phase(
            self.snapshot,
            self.pending,
            self.rng,
        )
        self.events.extend(events)
        return self.snapshot


def role_catalog() -> RoleCatalog:
    return RoleCatalog(
        roles={
            ROLE_PLAIN: RoleDefinition(faction=FACTION_VILLAGE, abilities=()),
            ROLE_SHADOW: RoleDefinition(
                faction=FACTION_WEREWOLF,
                abilities=(ABILITY_NIGHT_ATTACK, ABILITY_PACK_KNOWLEDGE),
            ),
            ROLE_READER: RoleDefinition(faction=FACTION_VILLAGE, abilities=(ABILITY_INSPECT,)),
            ROLE_SHIELD: RoleDefinition(faction=FACTION_VILLAGE, abilities=(ABILITY_GUARD,)),
        }
    )


def local_rules(*, random_tie: bool = False) -> LocalRules:
    return LocalRules(
        allow_self_vote=False,
        allow_vote_revision=False,
        allow_night_action_revision=False,
        enable_first_night_attack=True,
        enable_no_elimination_on_tie=not random_tie,
        enable_random_elimination_on_tie=random_tie,
        allow_knight_self_guard=True,
        allow_knight_repeat_guard=True,
        allow_seer_self_inspect=False,
        allow_werewolf_friendly_fire=False,
        reveal_role_on_death=False,
    )


def mvp_config(*, random_tie: bool = False) -> GameConfig:
    return GameConfig(
        player_count=5,
        role_counts={
            ROLE_SHADOW: 1,
            ROLE_READER: 1,
            ROLE_SHIELD: 1,
            ROLE_PLAIN: 2,
        },
        rules=local_rules(random_tie=random_tie),
        roles=role_catalog(),
    )


def fixed_players() -> list[Player]:
    return [
        Player(id="p1", name="Alice", role=ROLE_SHADOW),
        Player(id="p2", name="Bob", role=ROLE_READER),
        Player(id="p3", name="Chika", role=ROLE_SHIELD),
        Player(id="p4", name="Dan", role=ROLE_PLAIN),
        Player(id="p5", name="Eve", role=ROLE_PLAIN),
    ]


def start_fixed_run(
    *,
    random_tie: bool = False,
) -> HeadlessRun:
    rng = random.Random(7)
    snapshot, events = start_game(
        mvp_config(random_tie=random_tie),
        fixed_players(),
        rng,
    )
    return HeadlessRun(
        snapshot=snapshot,
        pending=PendingActions(),
        rng=rng,
        events=list(events),
    )


def advance_to_voting(run: HeadlessRun) -> None:
    run.advance()
    run.advance()
    assert run.snapshot.phase is Phase.VOTING


def test_game_config_validates_role_counts() -> None:
    with pytest.raises(ValidationError):
        GameConfig(
            player_count=5,
            role_counts={ROLE_SHADOW: 1, ROLE_PLAIN: 3},
            rules=local_rules(),
            roles=role_catalog(),
        )


def test_start_game_is_headless_and_returns_events() -> None:
    run = start_fixed_run()

    snapshot = run.snapshot

    assert snapshot.phase is Phase.NIGHT
    assert snapshot.day == 1
    assert snapshot.players["p1"].role == ROLE_SHADOW
    assert run.events[0].event_type == "game_started"
    assert run.events[0].payload["role_counts"] == {
        ROLE_SHADOW: 1,
        ROLE_READER: 1,
        ROLE_SHIELD: 1,
        ROLE_PLAIN: 2,
    }


def test_observation_hides_secret_roles_but_shows_allowed_knowledge() -> None:
    run = start_fixed_run()

    seer_observation = run.observe("p2")
    wolf_observation = run.observe("p1")

    assert seer_observation.known_roles == {"p2": ROLE_READER}
    assert {player.id: player.role for player in seer_observation.players} == {
        "p1": None,
        "p2": ROLE_READER,
        "p3": None,
        "p4": None,
        "p5": None,
    }
    assert wolf_observation.known_roles == {"p1": ROLE_SHADOW}


def test_night_actions_resolve_guard_and_private_seer_knowledge() -> None:
    run = start_fixed_run()

    run.submit(Action.attack("p1", "p4"))
    run.submit(Action.inspect("p2", "p1"))
    run.submit(Action.guard("p3", "p4"))
    snapshot = run.advance()

    assert snapshot.phase is Phase.DAY_DISCUSSION
    assert snapshot.players["p4"].status is PlayerStatus.ALIVE
    assert snapshot.history.nights[-1].protected_player_id == "p4"
    assert snapshot.history.nights[-1].killed_player_id is None
    assert run.observe("p2").known_roles["p1"] == ROLE_SHADOW
    assert "p1" not in run.observe("p4").known_roles


def test_vote_resolution_eliminates_player_and_finishes_game() -> None:
    run = start_fixed_run()
    advance_to_voting(run)

    for voter_id in ["p2", "p3", "p4", "p5"]:
        run.submit(Action.vote(voter_id, "p1"))
    run.submit(Action.vote("p1", "p5"))
    snapshot = run.advance()

    assert snapshot.phase is Phase.FINISHED
    assert snapshot.players["p1"].status is PlayerStatus.DEAD
    assert snapshot.history.votes[-1].eliminated_player_id == "p1"
    assert snapshot.win_result is not None
    assert snapshot.win_result.winner == FACTION_VILLAGE


def test_vote_tie_policy_can_leave_everyone_alive() -> None:
    run = start_fixed_run()
    advance_to_voting(run)

    run.submit(Action.vote("p1", "p4"))
    run.submit(Action.vote("p2", "p4"))
    run.submit(Action.vote("p3", "p5"))
    run.submit(Action.vote("p4", "p5"))
    snapshot = run.advance()

    assert snapshot.phase is Phase.NIGHT
    assert snapshot.day == 2
    assert snapshot.history.votes[-1].eliminated_player_id is None
    assert snapshot.history.votes[-1].tied_player_ids == ["p4", "p5"]
    assert snapshot.history.votes[-1].missing_voter_ids == ["p5"]


def test_invalid_actions_raise_safe_game_errors() -> None:
    run = start_fixed_run()

    with pytest.raises(GameError):
        run.submit(Action.vote("p1", "p2"))

    with pytest.raises(GameError):
        run.submit(Action.inspect("p4", "p1"))


def test_day_speech_is_only_recorded_during_discussion() -> None:
    run = start_fixed_run()

    with pytest.raises(GameError):
        run.submit(Action.speech("p2", "too early"))

    run.advance()
    run.submit(Action.speech("p2", "I have a read."))

    assert run.snapshot.history.speeches[-1].message == "I have a read."
    assert run.snapshot.history.speeches[-1].day == 1
    assert run.observe("p2").available_actions == []
    with pytest.raises(GameError):
        run.submit(Action.speech("p2", "same day duplicate"))


def test_day_speech_limit_resets_on_next_day() -> None:
    run = start_fixed_run()
    run.advance()
    run.submit(Action.speech("p2", "day one"))
    run.advance()
    run.advance()
    run.advance()

    assert run.snapshot.phase is Phase.DAY_DISCUSSION
    assert run.snapshot.day == 2
    assert run.observe("p2").available_actions == [ActionType.SPEECH]


def test_vote_and_night_actions_are_single_submission_by_default() -> None:
    run = start_fixed_run()

    run.submit(Action.attack("p1", "p4"))
    with pytest.raises(GameError):
        run.submit(Action.attack("p1", "p5"))

    run.advance()
    run.advance()
    run.submit(Action.vote("p2", "p1"))
    assert run.observe("p2").available_actions == []
    with pytest.raises(GameError):
        run.submit(Action.vote("p2", "p4"))
