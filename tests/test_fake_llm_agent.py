import random

from werewolf_agent.agents import FakeLlmAgent
from werewolf_agent.domain.models import (
    AgentAction,
    Game,
    GameConfig,
    KnightGuardAction,
    PassAction,
    Phase,
    PlayerConfig,
    Role,
    SeerInspectAction,
    SpeechAction,
    VoteAction,
    WerewolfAttackAction,
)


def config() -> GameConfig:
    return GameConfig(
        game_id="fake-game",
        player_count=5,
        role_counts={
            Role.WEREWOLF: 1,
            Role.SEER: 1,
            Role.KNIGHT: 1,
            Role.VILLAGER: 2,
        },
        seed=11,
    )


def players() -> list[PlayerConfig]:
    return [
        PlayerConfig(player_id="p1", name="Alice", role=Role.WEREWOLF),
        PlayerConfig(player_id="p2", name="Bob", role=Role.SEER),
        PlayerConfig(player_id="p3", name="Chika", role=Role.KNIGHT),
        PlayerConfig(player_id="p4", name="Dan", role=Role.VILLAGER),
        PlayerConfig(player_id="p5", name="Eve", role=Role.VILLAGER),
    ]


def start_game() -> Game:
    return Game.start(config=config(), players=players(), rng=random.Random(11))


def test_fake_llm_returns_role_specific_night_actions() -> None:
    game = start_game()

    wolf_action = FakeLlmAgent("p1", rng=random.Random(1)).act(game.observation_for("p1"))
    seer_action = FakeLlmAgent("p2", rng=random.Random(1)).act(game.observation_for("p2"))
    knight_action = FakeLlmAgent("p3", rng=random.Random(1)).act(game.observation_for("p3"))
    villager_action = FakeLlmAgent("p4", rng=random.Random(1)).act(game.observation_for("p4"))

    assert isinstance(wolf_action, WerewolfAttackAction)
    assert wolf_action.target_id != "p1"
    assert isinstance(seer_action, SeerInspectAction)
    assert seer_action.target_id != "p2"
    assert isinstance(knight_action, KnightGuardAction)
    assert isinstance(villager_action, PassAction)


def test_fake_llm_is_seed_deterministic_for_same_observation() -> None:
    game = start_game()
    observation = game.observation_for("p1")

    action_a = FakeLlmAgent("p1", rng=random.Random(99)).act(observation)
    action_b = FakeLlmAgent("p1", rng=random.Random(99)).act(observation)

    assert action_a == action_b


def test_fake_llm_day_and_vote_actions_match_phase() -> None:
    game = start_game()
    game.advance_phase()

    speech = FakeLlmAgent("p2", rng=random.Random(3)).act(game.observation_for("p2"))
    assert isinstance(speech, SpeechAction)
    assert speech.message

    game.advance_phase()
    vote = FakeLlmAgent("p2", rng=random.Random(3)).act(game.observation_for("p2"))
    assert isinstance(vote, VoteAction)
    assert vote.target_id != "p2"


def test_fake_llm_actions_are_accepted_by_game() -> None:
    game = start_game()
    agents = {
        player.player_id: FakeLlmAgent(player.player_id, rng=random.Random(5))
        for player in players()
    }

    for player_id, agent in agents.items():
        action = agent.act(game.observation_for(player_id))
        _submit_if_supported(game, action)
    game.advance_phase()

    for player in game.snapshot().players.values():
        if player.player_id in agents and player.status.value == "alive":
            action = agents[player.player_id].act(game.observation_for(player.player_id))
            _submit_if_supported(game, action)
    game.advance_phase()

    assert game.phase is Phase.VOTING


def _submit_if_supported(game: Game, action: AgentAction) -> None:
    if isinstance(action, SpeechAction):
        game.submit_day_action(action)
    elif isinstance(action, VoteAction):
        game.submit_vote(action)
    elif isinstance(action, (WerewolfAttackAction, SeerInspectAction, KnightGuardAction)):
        game.submit_night_action(action)
