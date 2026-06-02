import sys
from types import SimpleNamespace

from werewolf_agent.domain.game.models import (
    GameHistory,
    Observation,
    Phase,
    Player,
    PlayerStatus,
    SpeechRecord,
    VoteResult,
)
from werewolf_agent.domain.llm.service import LangChainDecisionProvider
from werewolf_agent.interface.runtime.resources import load_llm_definitions
from werewolf_agent.usecase.internal.agents import (
    _agent_observation_from_game,
    langchain_agent_factory,
)
from werewolf_agent.usecase.jobs import LlmProviderConfig


def test_agent_observation_from_game_carries_public_history_only() -> None:
    game_observation = Observation(
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


def test_langchain_agent_factory_uses_fake_decision_fixture() -> None:
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )

    factory = langchain_agent_factory(
        LlmProviderConfig(
            provider="fake",
            model="fake-list-llm",
            base_url="",
            api_key="",
            timeout_seconds=30.0,
            max_retries=2,
            temperature=0.7,
        ),
        definitions=definitions,
    )

    assert isinstance(factory.provider, LangChainDecisionProvider)
    assert factory.provider.fake_responses is definitions.fake_responses
    assert factory.provider.model is None


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
            temperature=0.2,
        ),
        definitions=definitions,
    )

    assert isinstance(factory.provider, LangChainDecisionProvider)
    assert isinstance(factory.provider.model, FakeChatOpenAI)
    assert factory.provider.fake_responses is None
    assert captured_kwargs == [
        {
            "model": "local-model",
            "api_key": "lm-studio",
            "temperature": 0.2,
            "timeout": 45.0,
            "max_retries": 3,
            "base_url": "http://127.0.0.1:1234/v1",
        }
    ]


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
            temperature=0.7,
        ),
        definitions=definitions,
    )

    assert isinstance(factory.provider, LangChainDecisionProvider)
    assert isinstance(factory.provider.model, FakeChatOpenAI)
    assert factory.provider.fake_responses is None
    assert captured_kwargs == [
        {
            "model": "gpt-4.1-mini",
            "api_key": "sk-test",
            "temperature": 0.7,
            "timeout": 30.0,
            "max_retries": 2,
        }
    ]
