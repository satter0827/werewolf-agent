"""標準ライブラリAgent SDKの外部注入契約を検証する."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from werewolf_agent.agents import (
    AgentAbility,
    AgentContext,
    AgentDecisionError,
    AgentIdentity,
    AgentObservation,
    AgentSession,
    AgentSpec,
    AgentWorld,
    DecisionOption,
    DecisionRequest,
    DecisionResponse,
    DecisionTrace,
    ObservedPlayer,
    PublicTimelineEvent,
    RandomLegalAgentFactory,
    assert_agent_factory_contract,
)


class _Session:
    def __init__(self, context: AgentContext) -> None:
        self.context = context
        self.closed = False

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        assert request.context == self.context
        option = request.options[0]
        return DecisionResponse(
            action_type=option.action_type,
            target_id=option.legal_target_ids[0] if option.legal_target_ids else None,
        )

    def close(self) -> None:
        self.closed = True


class _Factory:
    @property
    def spec(self) -> AgentSpec:
        return AgentSpec("external", "1.0.0", "1" * 64, {"mode": "test"})

    def create(self, context: AgentContext) -> AgentSession:
        return _Session(context)


def _request(context: AgentContext) -> DecisionRequest:
    me = ObservedPlayer(context.player_id, "Alice", True)
    other = ObservedPlayer("p2", "Bob", True)
    return DecisionRequest(
        decision_id="decision-1",
        context=context,
        observation=AgentObservation(
            phase="voting",
            day=1,
            me=me,
            players=(me, other),
            known_roles={context.player_id: "villager"},
        ),
        public_timeline=(PublicTimelineEvent(1, "speech", 1, "p2", {"message": ["確認します"]}),),
        options=(DecisionOption("vote", legal_target_ids=("p2",)),),
        decision_seed=17,
        deadline_at=datetime(2030, 1, 1, tzinfo=UTC),
    )


def test_external_factory_creates_state_isolated_sessions() -> None:
    factory = _Factory()
    first_context = AgentContext("s1", "g1", "p1", 11)
    second_context = AgentContext("s2", "g1", "p2", 12)

    first = factory.create(first_context)
    second = factory.create(second_context)

    assert isinstance(first, AgentSession)
    assert first is not second
    assert first.decide(_request(first_context)).action_type == "vote"


def test_external_factory_uses_the_public_contract_kit() -> None:
    """利用者が公開APIだけでSession分離と応答を検証できる。"""
    contexts = (
        AgentContext("s1", "g1", "p1", 11),
        AgentContext("s2", "g1", "p3", 12),
    )
    assert_agent_factory_contract(_Factory(), requests=tuple(map(_request, contexts)))


def test_request_rejects_secret_or_illegal_player_references() -> None:
    context = AgentContext("s1", "g1", "p1", 11)
    me = ObservedPlayer("p1", "Alice", True)

    with pytest.raises(ValueError, match="visible players"):
        AgentObservation(
            phase="voting",
            day=1,
            me=me,
            players=(me,),
            known_roles={"secret-player": "werewolf"},
        )
    with pytest.raises(ValueError, match="legal targets"):
        DecisionRequest(
            decision_id="decision-1",
            context=context,
            observation=AgentObservation("voting", 1, me, (me,)),
            public_timeline=(),
            options=(DecisionOption("vote", legal_target_ids=("secret-player",)),),
            decision_seed=17,
        )
    with pytest.raises(ValueError, match="timeline actors"):
        DecisionRequest(
            decision_id="decision-1",
            context=context,
            observation=AgentObservation("voting", 1, me, (me,)),
            public_timeline=(PublicTimelineEvent(1, "speech", 1, "secret-player"),),
            options=(DecisionOption("pass"),),
            decision_seed=17,
        )


def test_contract_values_deeply_freeze_diagnostics_and_public_payloads() -> None:
    spec = AgentSpec("external", "1.0.0", "1" * 64, {"nested": {"items": [1, 2]}})
    request = _request(AgentContext("s1", "g1", "p1", 11))

    assert spec.parameters["nested"] == {"items": (1, 2)}
    assert request.public_timeline[0].payload["message"] == ("確認します",)
    with pytest.raises(TypeError):
        spec.parameters["other"] = True  # type: ignore[index]
    with pytest.raises(ValueError, match="mapping keys"):
        AgentSpec("external", "1.0.0", "1" * 64, {1: "invalid"})  # type: ignore[dict-item]
    with pytest.raises(ValueError, match="JSON-compatible"):
        AgentSpec("external", "1.0.0", "1" * 64, {"runtime": object()})


def test_contract_rejects_non_string_text_without_leaking_attribute_errors() -> None:
    """外部実装の型違反を一貫した契約エラーとして拒否する."""
    with pytest.raises(ValueError, match="agent_id must be a string"):
        AgentSpec(1, "1.0.0", "1" * 64)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="speech must be a string"):
        RandomLegalAgentFactory(1)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", (float("nan"), float("inf"), float("-inf")))
@pytest.mark.parametrize("field_name", ("confidence", "beliefs"))
def test_decision_response_rejects_non_finite_probabilities(
    value: float,
    field_name: str,
) -> None:
    """外部Agentの非有限確率をartifactへ到達する前に拒否する."""
    arguments = {field_name: value if field_name == "confidence" else {"p1": value}}

    with pytest.raises(ValueError, match="finite and between 0 and 1"):
        DecisionResponse("pass", **arguments)  # type: ignore[arg-type]


def test_observation_separates_owner_identity_from_public_world() -> None:
    """本人知識と全員に公開する世界観を型付きの別領域として保持する."""
    me = ObservedPlayer("p1", "Alice", True)
    other = ObservedPlayer("p2", "Bob", True)
    identity = AgentIdentity(
        role_id="oracle",
        role_name="観測者",
        identity_faction_id="village",
        identity_faction_name="探索側",
        victory_team_id="village",
        victory_team_name="探索側",
        objective="情報を集める",
        abilities=(AgentAbility("scan", "観測", "inspect", 1),),
    )
    world = AgentWorld(
        theme_id="laboratory",
        theme_name="研究施設",
        premise="正体を隠した侵入者を見つける",
        setup_checksum="a" * 64,
        mechanics_checksum="b" * 64,
        relevant_rules={"allow_self_vote": False},
        action_names={"vote": "投票する"},
        phase_names={"night": "夜"},
    )

    observation = AgentObservation(
        "night",
        1,
        me,
        (me, other),
        known_roles={"p1": "oracle"},
        known_factions={"p1": "village"},
        identity=identity,
        world=world,
    )

    assert observation.identity == identity
    assert observation.world == world
    assert observation.world.relevant_rules == {"allow_self_vote": False}
    with pytest.raises(TypeError):
        observation.world.action_names["vote"] = "変更"  # type: ignore[index]


def test_observation_rejects_identity_inconsistent_with_self_knowledge() -> None:
    """同じ本人情報を二つの表現で食い違わせない."""
    me = ObservedPlayer("p1", "Alice", True)
    identity = AgentIdentity(
        "oracle",
        "観測者",
        "village",
        "探索側",
        "village",
        "探索側",
        "情報を集める",
    )

    with pytest.raises(ValueError, match="identity role"):
        AgentObservation(
            "night",
            1,
            me,
            (me,),
            known_roles={"p1": "werewolf"},
            identity=identity,
        )


@pytest.mark.parametrize(
    ("field_name", "position"), (("identity_faction_id", 2), ("victory_team_id", 4))
)
def test_agent_identity_rejects_noncanonical_faction_ids(
    field_name: str,
    position: int,
) -> None:
    """Domainと同じ正規faction IDだけを外部Agent契約で受理する."""
    values = ["oracle", "観測者", "village", "探索側", "village", "探索側", "目的"]
    values[position] = "town"

    with pytest.raises(ValueError, match=field_name):
        AgentIdentity(*values)


def test_agent_decision_error_freezes_safe_diagnostics() -> None:
    """予定された失敗を安定codeとimmutableな診断値で通知する."""
    error = AgentDecisionError("agent.invalid_response", {"stage": "schema"})

    assert str(error) == "agent.invalid_response"
    assert error.code == "agent.invalid_response"
    assert error.diagnostics == {"stage": "schema"}
    with pytest.raises(TypeError):
        error.diagnostics["stage"] = "changed"  # type: ignore[index]


@pytest.mark.parametrize(
    "build",
    (
        lambda: AgentContext("s1", "g1", "p1", True),
        lambda: AgentObservation(
            "night",
            True,
            ObservedPlayer("p1", "Alice", True),
            (ObservedPlayer("p1", "Alice", True),),
        ),
        lambda: DecisionOption("speech", message_max_chars=True),
    ),
)
def test_contract_rejects_boolean_values_for_integer_fields(
    build: Callable[[], object],
) -> None:
    """Pythonでintのsubclassであるboolを数値契約として受理しない."""
    with pytest.raises(ValueError, match="must be an integer"):
        build()


def test_agent_world_requires_sha256_provenance() -> None:
    """実験とtraceへ使用するchecksumを曖昧な文字列にしない."""
    with pytest.raises(ValueError, match="setup_checksum"):
        AgentWorld("theme", "Theme", "Premise", "not-a-checksum", "b" * 64)


def test_decision_trace_requires_an_outcome_and_a_fallback_response() -> None:
    """分析不能な空traceと応答のないfallbackを拒否する."""
    spec = AgentSpec("external", "1.0.0", "1" * 64)
    with pytest.raises(ValueError, match="response or error_code"):
        DecisionTrace("decision-1", spec, None, 1)
    with pytest.raises(ValueError, match="fallback trace must contain a response"):
        DecisionTrace("decision-1", spec, None, 1, True, "agent_timeout")
    with pytest.raises(ValueError, match="fallback trace must contain an error_code"):
        DecisionTrace("decision-1", spec, DecisionResponse("pass"), 1, True)
    with pytest.raises(ValueError, match="successful trace must not contain an error_code"):
        DecisionTrace("decision-1", spec, DecisionResponse("pass"), 1, False, "agent_fault")

    response = DecisionResponse("pass")
    trace = DecisionTrace("decision-1", spec, response, 1, True, "agent_timeout")

    assert trace.agent_spec == spec
    assert trace.response == response
    assert trace.fallback_used
