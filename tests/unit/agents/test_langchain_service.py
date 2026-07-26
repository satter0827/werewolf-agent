import pytest

from werewolf_agent.adapters.llm.langchain.constants import (
    DECISION_GRAPH_REVISION,
    LLM_SPEECH_MESSAGE_MAX_CHARS,
    LLM_SPEECH_PROMPT_MAX_CHARS,
    PROMPT_RECENT_SPEECH_LIMIT,
    PROMPT_RECENT_VOTE_ROUND_LIMIT,
)
from werewolf_agent.adapters.llm.langchain.prompting import (
    _compact_observation,
    _decision_format_instructions,
    _prompt_inputs,
)
from werewolf_agent.adapters.llm.langchain.service import (
    LangChainDecisionProvider,
)
from werewolf_agent.adapters.resources import load_llm_definitions
from werewolf_agent.agents.definitions import (
    FakeDecisionCatalog,
    PromptDefinition,
    PromptMessageDefinition,
)
from werewolf_agent.agents.models import (
    AgentActionType,
    AgentGameContext,
    AgentObservation,
    AgentPhase,
    AgentPlayerStatus,
    VisiblePlayer,
)
from werewolf_agent.agents.tracing import LlmInvocationTrace


def players() -> list[VisiblePlayer]:
    return [
        VisiblePlayer(id="p1", name="Alice", status=AgentPlayerStatus.ALIVE),
        VisiblePlayer(id="p2", name="Bob", status=AgentPlayerStatus.ALIVE),
        VisiblePlayer(id="p3", name="Chika", status=AgentPlayerStatus.ALIVE),
        VisiblePlayer(id="p4", name="Dan", status=AgentPlayerStatus.ALIVE),
        VisiblePlayer(id="p5", name="Eve", status=AgentPlayerStatus.ALIVE),
    ]


def observation(
    *,
    player_id: str = "p1",
    role: str = "werewolf",
    phase: AgentPhase = AgentPhase.NIGHT,
    known_roles: dict[str, str] | None = None,
    available_actions: list[AgentActionType] | None = None,
) -> AgentObservation:
    visible_players = players()
    me = next(player for player in visible_players if player.id == player_id)
    actions = (
        available_actions if available_actions is not None else _available_actions(role, phase)
    )
    return AgentObservation(
        phase=phase,
        day=1,
        me=me,
        role=role,
        players=visible_players,
        known_roles=known_roles or {},
        available_actions=actions,
        legal_targets={
            action: _legal_targets(action, player_id, visible_players, known_roles or {})
            for action in actions
            if action
            in {
                AgentActionType.VOTE,
                AgentActionType.WEREWOLF_ATTACK,
                AgentActionType.SEER_INSPECT,
                AgentActionType.KNIGHT_GUARD,
                AgentActionType.APOTHECARY_HEAL,
                AgentActionType.APOTHECARY_POISON,
            }
        },
        speeches=[],
        vote_rounds=[],
    )


def _available_actions(role: str, phase: AgentPhase) -> list[AgentActionType]:
    if phase is AgentPhase.DAY_DISCUSSION:
        return [AgentActionType.SPEECH]
    if phase is AgentPhase.VOTING:
        return [AgentActionType.VOTE]
    if phase is AgentPhase.NIGHT:
        return {
            "werewolf": [AgentActionType.WEREWOLF_ATTACK],
            "seer": [AgentActionType.SEER_INSPECT],
            "knight": [AgentActionType.KNIGHT_GUARD],
            "villager": [],
        }[role]
    return []


def _legal_targets(
    action: AgentActionType,
    player_id: str,
    visible_players: list[VisiblePlayer],
    known_roles: dict[str, str],
) -> list[str]:
    candidates = [player.id for player in visible_players if player.id != player_id]
    if action is AgentActionType.KNIGHT_GUARD:
        return [player.id for player in visible_players]
    if action is AgentActionType.WEREWOLF_ATTACK:
        return [candidate for candidate in candidates if known_roles.get(candidate) != "werewolf"]
    return candidates


def provider() -> LangChainDecisionProvider:
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )
    return LangChainDecisionProvider(
        prompt=definitions.prompt,
        fake_responses=definitions.fake_responses,
    )


class RecordingTraceSink:
    def __init__(self) -> None:
        self.records: list[LlmInvocationTrace] = []

    def record_invocation(self, trace: LlmInvocationTrace) -> None:
        self.records.append(trace)


def test_prompt_resource_uses_mlflow_style_metadata_and_langchain_variables() -> None:
    prompt = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    ).prompt

    assert prompt.name == "werewolf-agent-decision"
    assert prompt.alias == "local"
    assert prompt.tags["task"] == "agent_decision"
    assert prompt.model_config_metadata["model_name"] == "fake-list-llm"
    assert prompt.response_format["schema"] == "AgentDecision"
    assert "{{player_id}}" in prompt.messages[-1].content
    assert "{{selected_action}}" in prompt.messages[-1].content
    assert prompt.messages[-1].variables() >= {"player_id", "selected_action"}


def test_fake_response_resource_uses_action_response_pools() -> None:
    fake_responses = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    ).fake_responses

    assert fake_responses.name == "werewolf-agent-fake-decisions"
    assert fake_responses.tags["provider"] == "fake-list-llm"
    assert len(fake_responses.templates[AgentActionType.SPEECH.value]) > 1
    assert fake_responses.render(
        AgentActionType.VOTE.value,
        context={
            "player_id": "p1",
            "target_id": "p2",
            "target_name": "Bob",
        },
    ).startswith('{"type":"vote"')


def test_prompt_resource_rejects_missing_variable_metadata() -> None:
    with pytest.raises(ValueError, match="message variables missing"):
        PromptDefinition(
            name="bad",
            version=1,
            alias="local",
            input_variables=["player_id"],
            response_format={"schema": "AgentDecision"},
            messages=[
                PromptMessageDefinition(
                    role="human",
                    content="{{player_id}} {{missing}}",
                )
            ],
        )


def test_compact_observation_keeps_only_recent_public_history() -> None:
    base_observation = observation(player_id="p2", role="seer", phase=AgentPhase.VOTING)
    agent_observation = AgentObservation.model_validate(
        {
            **base_observation.model_dump(mode="json"),
            "speeches": [
                {"player_id": "p1", "message": f"speech-{index}"}
                for index in range(PROMPT_RECENT_SPEECH_LIMIT + 2)
            ],
            "vote_rounds": [
                {
                    "day": index,
                    "votes": {"p1": "p2"},
                    "counts": {"p2": 1},
                    "eliminated_player_id": None,
                }
                for index in range(PROMPT_RECENT_VOTE_ROUND_LIMIT + 2)
            ],
        }
    )

    compact = _compact_observation(agent_observation)

    assert [speech["message"] for speech in compact["speeches"]] == [
        f"speech-{index}" for index in range(2, PROMPT_RECENT_SPEECH_LIMIT + 2)
    ]
    assert [vote_round["day"] for vote_round in compact["vote_rounds"]] == list(
        range(2, PROMPT_RECENT_VOTE_ROUND_LIMIT + 2)
    )


def test_decision_format_instructions_leave_speech_validation_headroom() -> None:
    instructions = _decision_format_instructions()
    assert (
        f"Keep a speech message concise: at most {LLM_SPEECH_PROMPT_MAX_CHARS} characters."
        in instructions
    )
    assert 'include one non-null "target_id" copied exactly from legal_targets_json' in instructions
    assert 'For "speech", include a non-empty "message" and omit "target_id".' in instructions
    assert LLM_SPEECH_PROMPT_MAX_CHARS < LLM_SPEECH_MESSAGE_MAX_CHARS


def test_langchain_fake_provider_returns_role_specific_night_decisions() -> None:
    wolf_decision = provider().choose_decision(
        "p1",
        observation(
            player_id="p1",
            role="werewolf",
            known_roles={"p1": "werewolf"},
        ),
    )
    seer_decision = provider().choose_decision(
        "p2",
        observation(player_id="p2", role="seer"),
    )
    knight_decision = provider().choose_decision(
        "p3",
        observation(player_id="p3", role="knight"),
    )
    villager_decision = provider().choose_decision(
        "p4",
        observation(player_id="p4", role="villager"),
    )

    assert wolf_decision.type is AgentActionType.WEREWOLF_ATTACK
    assert wolf_decision.target_id != "p1"
    assert seer_decision.type is AgentActionType.SEER_INSPECT
    assert seer_decision.target_id != "p2"
    assert knight_decision.type is AgentActionType.KNIGHT_GUARD
    assert villager_decision.type is AgentActionType.PASS


def test_langchain_fake_provider_day_and_vote_decisions_match_phase() -> None:
    speech = provider().choose_decision(
        "p2",
        observation(player_id="p2", role="seer", phase=AgentPhase.DAY_DISCUSSION),
    )
    vote = provider().choose_decision(
        "p2",
        observation(player_id="p2", role="seer", phase=AgentPhase.VOTING),
    )

    assert speech.type is AgentActionType.SPEECH
    assert speech.message
    assert vote.type is AgentActionType.VOTE
    assert vote.target_id != "p2"


@pytest.mark.parametrize(
    "action_type",
    [AgentActionType.APOTHECARY_HEAL, AgentActionType.APOTHECARY_POISON],
)
def test_langchain_fake_provider_supports_every_targeted_night_action(
    action_type: AgentActionType,
) -> None:
    decision = provider().choose_decision(
        "p2",
        observation(
            player_id="p2",
            role="apothecary",
            available_actions=[action_type],
        ),
    )

    assert decision.type is action_type
    assert decision.target_id in {"p1", "p3", "p4", "p5"}


def test_langchain_fake_provider_passes_when_observation_is_not_for_player() -> None:
    decision = provider().choose_decision(
        "p1",
        observation(player_id="p2", role="seer"),
    )

    assert decision.type is AgentActionType.PASS
    assert decision.reason == "observation belongs to another player"


def test_langchain_fake_provider_uses_deterministic_fallback_for_invalid_json() -> None:
    fake_responses = FakeDecisionCatalog.model_validate(
        {
            "name": "bad",
            "version": 1,
            "alias": "local",
            "templates": {
                "vote": "not json",
                "pass": '{"type":"pass","player_id":"$player_id","reason":"fallback"}',
            },
        }
    )
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )
    trace_sink = RecordingTraceSink()
    decision = LangChainDecisionProvider(
        prompt=definitions.prompt,
        fake_responses=fake_responses,
        trace_sink=trace_sink,
    ).choose_decision(
        "p2",
        observation(player_id="p2", role="seer", phase=AgentPhase.VOTING),
    )

    assert decision.type is AgentActionType.VOTE
    assert decision.target_id in {"p1", "p3", "p4", "p5"}
    trace = trace_sink.records[-1]
    assert trace.request_payload["graph_revision"] == DECISION_GRAPH_REVISION
    assert trace.request_payload["validation_status"] in {"fallback", "valid"}
    assert trace.latency_ms is not None

    repeated = LangChainDecisionProvider(
        prompt=definitions.prompt,
        fake_responses=fake_responses,
    ).choose_decision(
        "p2",
        observation(player_id="p2", role="seer", phase=AgentPhase.VOTING),
    )

    assert repeated.target_id == decision.target_id


def test_langchain_provider_parses_markdown_fenced_json_output() -> None:
    class FencedJsonModel:
        def invoke(self, _prompt_value: object) -> str:
            return (
                "```json\n"
                '{"type":"speech","player_id":"p1","target_id":"p1",'
                '"message":"extra","reason":"suspect"}\n'
                "```"
            )

    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )
    decision = LangChainDecisionProvider(
        prompt=definitions.prompt,
        model=FencedJsonModel(),
    ).choose_decision(
        "p2",
        observation(player_id="p2", role="seer", phase=AgentPhase.VOTING),
    )

    assert decision.type is AgentActionType.VOTE
    assert decision.player_id == "p2"
    assert decision.target_id == "p1"


def test_langchain_provider_replaces_invalid_target_with_deterministic_target() -> None:
    fake_responses = FakeDecisionCatalog.model_validate(
        {
            "name": "bad",
            "version": 1,
            "alias": "local",
            "templates": {
                "vote": (
                    '{"type":"vote","player_id":"$player_id",'
                    '"target_id":"missing","reason":"bad target"}'
                ),
                "pass": '{"type":"pass","player_id":"$player_id","reason":"fallback"}',
            },
        }
    )
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )
    decision = LangChainDecisionProvider(
        prompt=definitions.prompt,
        fake_responses=fake_responses,
    ).choose_decision(
        "p2",
        observation(player_id="p2", role="seer", phase=AgentPhase.VOTING),
    )

    assert decision.type is AgentActionType.VOTE
    assert decision.target_id in {"p1", "p3", "p4", "p5"}
    assert decision.reason


def test_standard_graph_adds_role_hint_to_prompt_context() -> None:
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )
    trace_sink = RecordingTraceSink()

    decision = LangChainDecisionProvider(
        prompt=definitions.prompt,
        fake_responses=definitions.fake_responses,
        trace_sink=trace_sink,
    ).choose_decision(
        "p1",
        observation(player_id="p1", role="werewolf", known_roles={"p1": "werewolf"}),
    )

    assert decision.type is AgentActionType.WEREWOLF_ATTACK
    assert trace_sink.records
    assert "role_hint:" in str(trace_sink.records[-1].prompt_messages)


def test_prompt_uses_theme_terms_for_visible_role_and_phase() -> None:
    themed_context = AgentGameContext(
        theme_id="starship",
        theme_name="宇宙船",
        premise="航行中の宇宙船です。",
        role_id="werewolf",
        role_name="擬態生命体",
        identity_faction="werewolf",
        identity_faction_name="擬態生命体側",
        victory_team="werewolf",
        victory_team_name="擬態生命体側",
        objective="乗組員に擬態して生き残ります。",
        phase_names={"night": "休眠時間"},
        setup_checksum="setup",
        mechanics_checksum="mechanics",
    )
    themed_observation = observation().model_copy(update={"game_context": themed_context})

    inputs = _prompt_inputs(
        "p1",
        themed_observation,
        selected_action=AgentActionType.WEREWOLF_ATTACK,
        parser=None,  # type: ignore[arg-type]
    )

    assert inputs["role"] == "擬態生命体"
    assert inputs["phase"] == "休眠時間"
    assert "乗組員に擬態" in inputs["game_context_json"]


def test_standard_graph_ranks_only_legal_targets() -> None:
    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )
    trace_sink = RecordingTraceSink()

    decision = LangChainDecisionProvider(
        prompt=definitions.prompt,
        fake_responses=definitions.fake_responses,
        trace_sink=trace_sink,
    ).choose_decision(
        "p2",
        observation(player_id="p2", role="seer", phase=AgentPhase.VOTING),
    )

    assert decision.type is AgentActionType.VOTE
    assert decision.target_id in {"p1", "p3", "p4", "p5"}


def test_trace_normalizes_provider_usage_without_estimating_tokens() -> None:
    class UsageResponse:
        content = '{"type":"speech","message":"確認します。"}'

        def model_dump(self, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return {
                "content": self.content,
                "usage_metadata": {
                    "input_tokens": 31,
                    "output_tokens": 9,
                    "total_tokens": 40,
                },
            }

    class UsageModel:
        def invoke(self, _prompt_value: object) -> UsageResponse:
            return UsageResponse()

    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )
    trace_sink = RecordingTraceSink()

    decision = LangChainDecisionProvider(
        prompt=definitions.prompt,
        model=UsageModel(),
        provider_name="local",
        model_name="usage-model",
        trace_sink=trace_sink,
        structured_output_mode="disabled",
    ).choose_decision(
        "p1",
        observation(player_id="p1", role="villager", phase=AgentPhase.DAY_DISCUSSION),
    )

    assert decision.type is AgentActionType.SPEECH
    trace = trace_sink.records[-1]
    assert trace.input_tokens == 31
    assert trace.output_tokens == 9
    assert trace.total_tokens == 40
    assert trace.usage_source == "usage_metadata"
    assert trace.prompt_characters > 0
    assert trace.response_bytes > 0


def test_langchain_ai_message_envelope_is_not_treated_as_agent_action() -> None:
    class AiMessageLike:
        content = (
            '```json\n{"type":"knight_guard","target_id":"p1",'
            '"message":"ignore envelope message"}\n```'
        )

        def model_dump(self, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return {
                "type": "ai",
                "content": self.content,
                "usage_metadata": {"input_tokens": 20, "output_tokens": 8},
            }

    class AiMessageModel:
        def invoke(self, _prompt_value: object) -> AiMessageLike:
            return AiMessageLike()

    definitions = load_llm_definitions(
        players_path=None,
        prompt_path=None,
        fake_responses_path=None,
    )
    trace_sink = RecordingTraceSink()

    decision = LangChainDecisionProvider(
        prompt=definitions.prompt,
        model=AiMessageModel(),
        trace_sink=trace_sink,
        structured_output_mode="disabled",
    ).choose_decision(
        "p2",
        observation(
            player_id="p2",
            role="knight",
            available_actions=[AgentActionType.KNIGHT_GUARD],
        ),
    )

    assert decision.type is AgentActionType.KNIGHT_GUARD
    assert decision.target_id == "p1"
    assert trace_sink.records[-1].repair_attempts == 0
