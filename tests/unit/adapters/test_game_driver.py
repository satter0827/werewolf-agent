import sys
from types import SimpleNamespace

import pytest

from werewolf_agent.adapters.agents import game_driver as agents
from werewolf_agent.adapters.agents.game_driver import (
    _agent_game_contexts,
    _agent_observation_from_game,
    langchain_agent_factory,
)
from werewolf_agent.adapters.llm.configuration import LlmProviderConfig
from werewolf_agent.adapters.llm.langchain.service import LangChainDecisionProvider
from werewolf_agent.adapters.llm.model_adapters import (
    FakeDecisionModel,
    LangChainChatDecisionModel,
)
from werewolf_agent.adapters.resources import load_llm_definitions
from werewolf_agent.contracts import (
    ERROR_CONTEXT_LLM_BASE_URL,
    ERROR_CONTEXT_LLM_ERROR_TYPE,
    ERROR_CONTEXT_LLM_PROVIDER,
    LLM_PROVIDER_ERROR_INVALID_MODELS_RESPONSE,
    LLM_PROVIDER_ERROR_NO_LOADED_MODEL,
    LlmProviderError,
)
from werewolf_agent.domain.state import (
    ActionType,
    GameHistory,
    GameView,
    Phase,
    Player,
    PlayerStatus,
    SpeechRecord,
    VoteResult,
)


def _lmstudio_auto_config() -> LlmProviderConfig:
    return LlmProviderConfig(
        provider="lmstudio",
        model="auto",
        base_url="http://127.0.0.1:1234/v1",
        api_key="",
        timeout_seconds=45.0,
        max_retries=3,
        max_tokens=128,
        temperature=0.2,
    )


def test_agent_observation_from_game_carries_public_history_only() -> None:
    game_observation = GameView(
        phase=Phase.VOTING,
        day=2,
        me=Player(id="p1", name="Alice", role="seer"),
        players=[
            Player(id="p1", name="Alice", role="seer"),
            Player(id="p2", name="Bob", status=PlayerStatus.ALIVE),
        ],
        known_roles={"p1": "seer"},
        history=GameHistory(
            speeches=[SpeechRecord(day=2, player_id="p2", message="I want to hear from Alice.")],
            votes=[
                VoteResult(
                    day=1,
                    votes={"p1": "p2"},
                    counts={"p2": 1},
                    eliminated_player_id=None,
                    tie_break_policy="no_elimination",
                )
            ],
        ),
    )

    agent_observation = _agent_observation_from_game(game_observation)

    assert agent_observation.speeches[0].player_id == "p2"
    assert agent_observation.speeches[0].message == "I want to hear from Alice."
    assert agent_observation.vote_rounds[0].votes == {"p1": "p2"}
    assert agent_observation.vote_rounds[0].counts == {"p2": 1}
    assert agent_observation.known_roles == {"p1": "seer"}


def test_agent_game_context_uses_theme_language_for_identity_and_objective() -> None:
    prepared = SimpleNamespace(
        config={
            "setup_document": {
                "mechanics": {
                    "roles": {
                        "werewolf": {
                            "identity_faction": "werewolf",
                            "victory_team": "werewolf",
                            "objective": "Reach parity with villagers.",
                            "abilities": ["night_attack"],
                        }
                    },
                    "abilities": {
                        "night_attack": {
                            "action": "werewolf_attack",
                            "effect": "attack",
                            "max_uses": None,
                        }
                    },
                    "rules": {"allow_night_action_revision": False},
                },
                "theme": {
                    "id": "starship",
                    "name": "宇宙船",
                    "premise": "航行中の宇宙船で擬態生命体を探します。",
                    "role_names": {"werewolf": "擬態生命体"},
                    "role_objectives": {
                        "werewolf": "擬態を保って乗組員を減らし、擬態生命体側を勝利させます。"
                    },
                    "faction_names": {"werewolf": "擬態生命体側"},
                    "ability_names": {"night_attack": "船内排除"},
                    "action_names": {"werewolf_attack": "排除"},
                    "phase_names": {"night": "休眠時間"},
                },
            },
            "setup_checksum": "setup-checksum",
            "mechanics_checksum": "mechanics-checksum",
        }
    )
    snapshot = SimpleNamespace(
        players={"p1": Player(id="p1", name="Alice", role="werewolf")},
        ability_uses={},
        phase=Phase.NIGHT,
    )

    context = _agent_game_contexts(prepared, snapshot)["p1"]

    assert context.role_name == "擬態生命体"
    assert context.identity_faction_name == "擬態生命体側"
    assert context.victory_team_name == "擬態生命体側"
    assert context.objective == "擬態を保って乗組員を減らし、擬態生命体側を勝利させます。"
    assert context.abilities[0].name == "船内排除"


def test_langchain_agent_factory_uses_fake_decision_fixture() -> None:
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )

    factory = langchain_agent_factory(
        LlmProviderConfig(
            provider="fake",
            model="fake-list-chat-model",
            base_url="",
            api_key="",
            timeout_seconds=30.0,
            max_retries=2,
            max_tokens=96,
            temperature=0.7,
        ),
        definitions=definitions,
    )

    assert isinstance(factory.provider, LangChainDecisionProvider)
    assert isinstance(factory.provider.decision_model, FakeDecisionModel)
    assert factory.provider.decision_model.catalog is definitions.fake_responses
    assert factory.provider.provider_name == "fake"
    assert factory.provider.model_name == "fake-list-chat-model"


def test_langchain_agent_factory_builds_lmstudio_chat_model(monkeypatch) -> None:
    captured_kwargs: list[dict[str, object]] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured_kwargs.append(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        SimpleNamespace(ChatOpenAI=FakeChatOpenAI),
    )
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )

    factory = langchain_agent_factory(
        LlmProviderConfig(
            provider="lmstudio",
            model="local-model",
            base_url="http://127.0.0.1:1234/v1",
            api_key="",
            timeout_seconds=45.0,
            max_retries=3,
            max_tokens=128,
            temperature=0.2,
        ),
        definitions=definitions,
    )

    assert isinstance(factory.provider, LangChainDecisionProvider)
    assert isinstance(factory.provider.decision_model, LangChainChatDecisionModel)
    assert isinstance(factory.provider.decision_model.model, FakeChatOpenAI)
    assert factory.provider.provider_name == "lmstudio"
    assert factory.provider.model_name == "local-model"
    assert factory.provider.decision_model.base_url == "http://127.0.0.1:1234/v1"
    assert factory.provider.decision_model.timeout_seconds == 45.0
    assert factory.provider.decision_model.max_tokens == 128
    assert captured_kwargs == [
        {
            "model": "local-model",
            "api_key": "lm-studio",
            "temperature": 0.2,
            "timeout": 45.0,
            "max_retries": 3,
            "max_tokens": 128,
            "base_url": "http://127.0.0.1:1234/v1",
        }
    ]


def test_langchain_agent_factory_auto_discovers_lmstudio_model(monkeypatch) -> None:
    captured_kwargs: list[dict[str, object]] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured_kwargs.append(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        SimpleNamespace(ChatOpenAI=FakeChatOpenAI),
    )
    monkeypatch.setattr(agents, "_lmstudio_model_id", lambda _config: "loaded-local-model")
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )

    factory = langchain_agent_factory(
        LlmProviderConfig(
            provider="lmstudio",
            model="auto",
            base_url="http://127.0.0.1:1234/v1",
            api_key="",
            timeout_seconds=45.0,
            max_retries=3,
            max_tokens=128,
            temperature=0.2,
        ),
        definitions=definitions,
    )

    assert isinstance(factory.provider, LangChainDecisionProvider)
    assert captured_kwargs[0]["model"] == "loaded-local-model"
    assert factory.provider.model_name == "loaded-local-model"


def test_lmstudio_auto_discovery_connection_error_falls_back_at_runtime(monkeypatch) -> None:
    captured_kwargs: list[dict[str, object]] = []

    class FailingChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured_kwargs.append(kwargs)

        def invoke(self, _prompt_value: object) -> object:
            raise RuntimeError("provider unavailable")

    def fail_models_request(*_args: object, **_kwargs: object) -> object:
        raise agents.httpx.ConnectError("server unavailable")

    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        SimpleNamespace(ChatOpenAI=FailingChatOpenAI),
    )
    monkeypatch.setattr(agents.httpx, "get", fail_models_request)
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )

    factory = langchain_agent_factory(
        _lmstudio_auto_config(),
        definitions=definitions,
    )
    observation = GameView(
        phase=Phase.DAY_DISCUSSION,
        day=1,
        me=Player(id="p1", name="Alice"),
        players=[Player(id="p1", name="Alice"), Player(id="p2", name="Bob")],
        available_actions=[ActionType.SPEECH],
    )

    action = factory.create("p1", seed=1).act(observation)

    assert captured_kwargs[0]["model"] == "auto"
    assert action.type is ActionType.SPEECH
    assert action.player_id == "p1"


def test_lmstudio_model_discovery_rejects_invalid_models_payload(monkeypatch) -> None:
    class InvalidModelsResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {"data": {"id": "not-a-list"}}

    monkeypatch.setattr(agents.httpx, "get", lambda *_args, **_kwargs: InvalidModelsResponse())

    with pytest.raises(LlmProviderError) as exc_info:
        agents._lmstudio_model_id(_lmstudio_auto_config())

    assert exc_info.value.context == {
        ERROR_CONTEXT_LLM_ERROR_TYPE: LLM_PROVIDER_ERROR_INVALID_MODELS_RESPONSE,
        ERROR_CONTEXT_LLM_PROVIDER: "lmstudio",
        ERROR_CONTEXT_LLM_BASE_URL: "http://127.0.0.1:1234/v1",
    }


def test_lmstudio_model_discovery_rejects_missing_loaded_model(monkeypatch) -> None:
    class EmptyModelsResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {"data": [{"id": ""}, {"object": "model"}]}

    monkeypatch.setattr(agents.httpx, "get", lambda *_args, **_kwargs: EmptyModelsResponse())

    with pytest.raises(LlmProviderError) as exc_info:
        agents._lmstudio_model_id(_lmstudio_auto_config())

    assert exc_info.value.context == {
        ERROR_CONTEXT_LLM_ERROR_TYPE: LLM_PROVIDER_ERROR_NO_LOADED_MODEL,
        ERROR_CONTEXT_LLM_PROVIDER: "lmstudio",
        ERROR_CONTEXT_LLM_BASE_URL: "http://127.0.0.1:1234/v1",
    }


def test_real_provider_invoke_error_uses_deterministic_fallback(monkeypatch) -> None:
    class FailingChatOpenAI:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def invoke(self, _prompt_value: object) -> object:
            raise RuntimeError("provider unavailable")

    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        SimpleNamespace(ChatOpenAI=FailingChatOpenAI),
    )
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )
    factory = langchain_agent_factory(
        LlmProviderConfig(
            provider="lmstudio",
            model="local-model",
            base_url="http://127.0.0.1:1234/v1",
            api_key="",
            timeout_seconds=45.0,
            max_retries=3,
            max_tokens=128,
            temperature=0.2,
        ),
        definitions=definitions,
    )
    observation = GameView(
        phase=Phase.DAY_DISCUSSION,
        day=1,
        me=Player(id="p1", name="Alice"),
        players=[Player(id="p1", name="Alice"), Player(id="p2", name="Bob")],
        available_actions=[ActionType.SPEECH],
    )

    action = factory.create("p1", seed=1).act(observation)

    assert action.type is ActionType.SPEECH
    assert action.player_id == "p1"


def test_langchain_agent_factory_builds_openai_chat_model(monkeypatch) -> None:
    captured_kwargs: list[dict[str, object]] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured_kwargs.append(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        SimpleNamespace(ChatOpenAI=FakeChatOpenAI),
    )
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )

    factory = langchain_agent_factory(
        LlmProviderConfig(
            provider="openai",
            model="gpt-4.1-mini",
            base_url="",
            api_key="sk-test",
            timeout_seconds=30.0,
            max_retries=2,
            max_tokens=96,
            temperature=0.7,
        ),
        definitions=definitions,
    )

    assert isinstance(factory.provider, LangChainDecisionProvider)
    assert isinstance(factory.provider.decision_model, LangChainChatDecisionModel)
    assert isinstance(factory.provider.decision_model.model, FakeChatOpenAI)
    assert factory.provider.provider_name == "openai"
    assert factory.provider.model_name == "gpt-4.1-mini"
    assert factory.provider.decision_model.timeout_seconds == 30.0
    assert factory.provider.decision_model.max_tokens == 96
    assert captured_kwargs == [
        {
            "model": "gpt-4.1-mini",
            "api_key": "sk-test",
            "temperature": 0.7,
            "timeout": 30.0,
            "max_retries": 2,
            "max_tokens": 96,
        }
    ]
