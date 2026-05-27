import random

from werewolf_agent.domain.models import (
    Action,
    ActionType,
    GameConfig,
    GameSnapshot,
    PendingActions,
    Phase,
    Player,
    PlayerStatus,
    Role,
)
from werewolf_agent.domain.service import (
    advance_phase,
    choose_dummy_action,
    observe,
    start_game,
    submit_action,
)


def config() -> GameConfig:
    return GameConfig(
        game_id="dummy-game",
        player_count=5,
        role_counts={
            Role.WEREWOLF: 1,
            Role.SEER: 1,
            Role.KNIGHT: 1,
            Role.VILLAGER: 2,
        },
        seed=11,
    )


def players() -> list[Player]:
    return [
        Player(id="p1", name="Alice", role=Role.WEREWOLF),
        Player(id="p2", name="Bob", role=Role.SEER),
        Player(id="p3", name="Chika", role=Role.KNIGHT),
        Player(id="p4", name="Dan", role=Role.VILLAGER),
        Player(id="p5", name="Eve", role=Role.VILLAGER),
    ]


def start_snapshot() -> GameSnapshot:
    snapshot, _events = start_game(config(), players(), random.Random(11))
    return snapshot


def test_dummy_agent_returns_role_specific_night_actions() -> None:
    snapshot = start_snapshot()

    wolf_action = choose_dummy_action("p1", observe(snapshot, "p1"), rng=random.Random(1))
    seer_action = choose_dummy_action("p2", observe(snapshot, "p2"), rng=random.Random(1))
    knight_action = choose_dummy_action("p3", observe(snapshot, "p3"), rng=random.Random(1))
    villager_action = choose_dummy_action("p4", observe(snapshot, "p4"), rng=random.Random(1))

    assert wolf_action.type is ActionType.WEREWOLF_ATTACK
    assert wolf_action.target_id != "p1"
    assert seer_action.type is ActionType.SEER_INSPECT
    assert seer_action.target_id != "p2"
    assert knight_action.type is ActionType.KNIGHT_GUARD
    assert villager_action.type is ActionType.PASS


def test_dummy_agent_is_seed_deterministic_for_same_observation() -> None:
    snapshot = start_snapshot()
    observation = observe(snapshot, "p1")

    action_a = choose_dummy_action("p1", observation, rng=random.Random(99))
    action_b = choose_dummy_action("p1", observation, rng=random.Random(99))

    assert action_a == action_b


def test_dummy_agent_day_and_vote_actions_match_phase() -> None:
    snapshot = start_snapshot()
    pending = PendingActions()
    snapshot, pending, _events = advance_phase(snapshot, pending, random.Random(11))

    speech = choose_dummy_action("p2", observe(snapshot, "p2"), rng=random.Random(3))
    assert speech.type is ActionType.SPEECH
    assert speech.message

    snapshot, pending, _events = advance_phase(snapshot, pending, random.Random(11))
    vote = choose_dummy_action("p2", observe(snapshot, "p2"), rng=random.Random(3))
    assert vote.type is ActionType.VOTE
    assert vote.target_id != "p2"


def test_dummy_agent_actions_are_accepted_by_game() -> None:
    snapshot = start_snapshot()
    pending = PendingActions()
    rng = random.Random(11)
    player_ids = [player.id for player in players()]
    for player_id in player_ids:
        action = choose_dummy_action(player_id, observe(snapshot, player_id), rng=random.Random(5))
        snapshot, pending, _events = _submit_if_supported(snapshot, pending, action)
    snapshot, pending, _events = advance_phase(snapshot, pending, rng)

    for player in snapshot.players.values():
        if player.id in player_ids and player.status is PlayerStatus.ALIVE:
            action = choose_dummy_action(
                player.id,
                observe(snapshot, player.id),
                rng=random.Random(5),
            )
            snapshot, pending, _events = _submit_if_supported(snapshot, pending, action)
    snapshot, pending, _events = advance_phase(snapshot, pending, rng)

    assert snapshot.phase is Phase.VOTING


def _submit_if_supported(
    snapshot: GameSnapshot,
    pending: PendingActions,
    action: Action,
) -> tuple[GameSnapshot, PendingActions, list[object]]:
    return submit_action(snapshot, pending, action)
