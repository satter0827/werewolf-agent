from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

from werewolf_agent.adapters.agents.game_driver import (
    AgentRuntime,
    _agent_game_contexts,
    _decide_action,
    _decision_request_from_game,
    _game_action_from_response,
    drive_prepared_game,
)
from werewolf_agent.adapters.llm.configuration import LlmProviderConfig
from werewolf_agent.adapters.resources import load_llm_definitions
from werewolf_agent.agents import (
    AgentContext,
    DecisionResponse,
    DecisionTrace,
    FaultAgentFactory,
    ScriptedAgentFactory,
)
from werewolf_agent.application import PreparedAdvanceGame
from werewolf_agent.domain import Action, Game, GameEvent
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

    context = AgentContext("session", "game", "p1", 1)
    result = _decision_request_from_game(
        context,
        observation,
        game_context=None,
        decision_seed=3,
    )

    assert result.options[0].ability_id == "custom_scan"
    assert result.options[0].legal_target_ids == ("p2",)


def test_agent_decision_maps_to_generic_domain_action() -> None:
    action = _game_action_from_response(
        "p1",
        DecisionResponse(
            action_type="use_ability",
            ability_id="custom_scan",
            target_id="p2",
        ),
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
            "setup_checksum": "1" * 64,
            "mechanics_checksum": "2" * 64,
            "scenario_name": "実験村",
            "scenario_prompt_premise": "公開された実験条件",
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
    assert contexts["p1"].theme_name == "実験村"
    assert contexts["p1"].premise == "公開された実験条件"


class _TraceSink:
    def __init__(self) -> None:
        self.records: list[DecisionTrace] = []

    def record_decision(self, trace: DecisionTrace) -> None:
        self.records.append(trace)


def test_driver_owns_deterministic_fallback_and_trace() -> None:
    observation = GameView(
        phase=Phase.VOTING,
        day=1,
        me=Player(id="p1", name="Alice", role="villager"),
        players=(
            Player(id="p1", name="Alice", role="villager"),
            Player(id="p2", name="Bob", role="werewolf"),
        ),
        available_actions=(AvailableAction(ActionType.VOTE),),
        legal_targets={"vote": ("p2",)},
        history=GameHistory(),
    )
    context = AgentContext("session", "game", "p1", 1)
    request = _decision_request_from_game(
        context,
        observation,
        game_context=None,
        decision_seed=3,
    )
    sink = _TraceSink()

    action = _decide_action(
        FaultAgentFactory("provider_failed"),
        context,
        request,
        trace_sink=sink,
    )

    assert action.target_id == "p2"
    assert sink.records[0].fallback_used
    assert sink.records[0].error_code == "provider_failed"


def test_driver_rejects_illegal_external_response_before_domain_mutation() -> None:
    observation = GameView(
        phase=Phase.VOTING,
        day=1,
        me=Player(id="p1", name="Alice", role="villager"),
        players=(
            Player(id="p1", name="Alice", role="villager"),
            Player(id="p2", name="Bob", role="werewolf"),
        ),
        available_actions=(AvailableAction(ActionType.VOTE),),
        legal_targets={"vote": ("p2",)},
        history=GameHistory(),
    )
    context = AgentContext("session", "game", "p1", 1)
    request = _decision_request_from_game(
        context,
        observation,
        game_context=None,
        decision_seed=3,
    )
    sink = _TraceSink()
    factory = ScriptedAgentFactory((DecisionResponse("vote", target_id="p1"),))

    action = _decide_action(factory, context, request, trace_sink=sink)

    assert action.target_id == "p2"
    assert sink.records[0].error_code == "agent_target_not_legal"


class _InjectedGame:
    def __init__(self) -> None:
        self.actions: list[Action] = []
        self.player = Player(id="p1", name="Alice", role="villager")

    def snapshot(self) -> SimpleNamespace:
        return SimpleNamespace(
            players={"p1": self.player},
            phase=Phase.NIGHT,
            day=1,
            ability_uses={},
        )

    def view_for(self, player_id: str) -> GameView:
        assert player_id == "p1"
        return GameView(
            phase=Phase.NIGHT,
            day=1,
            me=self.player,
            players=(self.player,),
            available_actions=(AvailableAction(ActionType.PASS),),
        )

    def submit(self, action: Action) -> tuple[GameEvent, ...]:
        self.actions.append(action)
        return ()


def test_prepared_game_uses_injected_factory_without_building_llm_provider() -> None:
    game = _InjectedGame()
    prepared = PreparedAdvanceGame(
        game_id="game-1",
        version=1,
        seed=7,
        config={"player_agent_types": {"p1": "external"}},
        game=cast(Game, game),
        created_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    runtime = AgentRuntime(
        config=LlmProviderConfig(
            provider="fake",
            model="unused",
            base_url="",
            api_key="",
            timeout_seconds=1,
            max_retries=0,
            max_tokens=1,
            temperature=0,
        ),
        definitions=load_llm_definitions(prompt_path=None, fake_responses_path=None),
        agent_factories={"p1": ScriptedAgentFactory((DecisionResponse(action_type="pass"),))},
    )

    driven = drive_prepared_game(prepared, runtime=runtime)

    assert driven.domain_events == ()
    assert len(game.actions) == 1
