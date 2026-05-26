import random

from werewolf_agent.agents import DummyAgent
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
from werewolf_agent.domain.service import advance_phase, observe, start_game, submit_action


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

    wolf_action = DummyAgent("p1", rng=random.Random(1)).act(observe(snapshot, "p1"))
    seer_action = DummyAgent("p2", rng=random.Random(1)).act(observe(snapshot, "p2"))
    knight_action = DummyAgent("p3", rng=random.Random(1)).act(observe(snapshot, "p3"))
    villager_action = DummyAgent("p4", rng=random.Random(1)).act(observe(snapshot, "p4"))

    assert wolf_action.type is ActionType.WEREWOLF_ATTACK
    assert wolf_action.target_id != "p1"
    assert seer_action.type is ActionType.SEER_INSPECT
    assert seer_action.target_id != "p2"
    assert knight_action.type is ActionType.KNIGHT_GUARD
    assert villager_action.type is ActionType.PASS


def test_dummy_agent_is_seed_deterministic_for_same_observation() -> None:
    snapshot = start_snapshot()
    observation = observe(snapshot, "p1")

    action_a = DummyAgent("p1", rng=random.Random(99)).act(observation)
    action_b = DummyAgent("p1", rng=random.Random(99)).act(observation)

    assert action_a == action_b


def test_dummy_agent_day_and_vote_actions_match_phase() -> None:
    snapshot = start_snapshot()
    pending = PendingActions()
    snapshot, pending, _events = advance_phase(snapshot, pending, random.Random(11))

    speech = DummyAgent("p2", rng=random.Random(3)).act(observe(snapshot, "p2"))
    assert speech.type is ActionType.SPEECH
    assert speech.message

    snapshot, pending, _events = advance_phase(snapshot, pending, random.Random(11))
    vote = DummyAgent("p2", rng=random.Random(3)).act(observe(snapshot, "p2"))
    assert vote.type is ActionType.VOTE
    assert vote.target_id != "p2"


def test_dummy_agent_actions_are_accepted_by_game() -> None:
    snapshot = start_snapshot()
    pending = PendingActions()
    rng = random.Random(11)
    agents = {player.id: DummyAgent(player.id, rng=random.Random(5)) for player in players()}

    for player_id, agent in agents.items():
        action = agent.act(observe(snapshot, player_id))
        snapshot, pending, _events = _submit_if_supported(snapshot, pending, action)
    snapshot, pending, _events = advance_phase(snapshot, pending, rng)

    for player in snapshot.players.values():
        if player.id in agents and player.status is PlayerStatus.ALIVE:
            action = agents[player.id].act(observe(snapshot, player.id))
            snapshot, pending, _events = _submit_if_supported(snapshot, pending, action)
    snapshot, pending, _events = advance_phase(snapshot, pending, rng)

    assert snapshot.phase is Phase.VOTING


def _submit_if_supported(
    snapshot: GameSnapshot,
    pending: PendingActions,
    action: Action,
) -> tuple[GameSnapshot, PendingActions, list[object]]:
    return submit_action(snapshot, pending, action)
