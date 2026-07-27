from types import SimpleNamespace

from werewolf_agent.adapters.agents.game_driver import (
    _agent_game_contexts,
    _agent_observation_from_game,
    _game_action_from_decision,
)
from werewolf_agent.agents.models import AgentDecision
from werewolf_agent.domain.state import (
    ActionType,
    AvailableAction,
    GameHistory,
    GameView,
    Phase,
    Player,
)


def test_agent_observation_preserves_generic_ability_options() -> None:
    observation = GameView(
        phase=Phase.NIGHT,
        day=1,
        me=Player(id="p1", name="Alice", role="oracle"),
        players=(Player(id="p1", name="Alice", role="oracle"), Player(id="p2", name="Bob")),
        available_actions=(AvailableAction(ActionType.USE_ABILITY, "custom_scan"),),
        legal_targets={"use_ability:custom_scan": ("p2",)},
        history=GameHistory(),
    )

    result = _agent_observation_from_game(observation)

    assert result.available_actions[0].ability_id == "custom_scan"
    assert result.legal_targets == {"use_ability:custom_scan": ["p2"]}


def test_agent_decision_maps_to_generic_domain_action() -> None:
    action = _game_action_from_decision(
        AgentDecision(
            type="use_ability",
            player_id="p1",
            ability_id="custom_scan",
            target_id="p2",
            reason="確認するため",
        )
    )

    assert action.type is ActionType.USE_ABILITY
    assert action.ability_id == "custom_scan"


def test_agent_context_reads_kind_without_role_name_branching() -> None:
    prepared = SimpleNamespace(
        config={
            "setup_document": {
                "mechanics": {
                    "roles": {
                        "oracle": {
                            "identity_faction": "village",
                            "victory_team": "village",
                            "abilities": ["custom_scan"],
                        }
                    },
                    "abilities": {"custom_scan": {"kind": "inspect", "max_uses": "unlimited"}},
                    "rules": {"allow_night_action_revision": False},
                },
                "theme": {
                    "id": "custom",
                    "name": "Custom",
                    "premise": "Test",
                    "role_names": {"oracle": "観測者"},
                    "role_objectives": {"oracle": "情報を集める"},
                    "faction_names": {"village": "探索側"},
                    "ability_names": {"custom_scan": "観測"},
                    "action_names": {"use_ability": "能力を使う"},
                    "phase_names": {"night": "夜"},
                },
            },
            "setup_checksum": "setup",
            "mechanics_checksum": "mechanics",
        }
    )
    snapshot = SimpleNamespace(
        players={"p1": Player(id="p1", name="Alice", role="oracle")},
        ability_uses={},
        phase=Phase.NIGHT,
    )

    contexts = _agent_game_contexts(prepared, snapshot)

    assert contexts["p1"].abilities[0].kind == "inspect"
    assert contexts["p1"].role_name == "観測者"
