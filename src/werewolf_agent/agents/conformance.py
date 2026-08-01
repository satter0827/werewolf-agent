"""外部Agent実装へ適用できる標準ライブラリ契約テストを提供する."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from werewolf_agent.agents.contracts import (
    AgentFactory,
    AgentSession,
    AgentSpec,
    DecisionOption,
    DecisionRequest,
    DecisionResponse,
)


def assert_agent_factory_contract(
    factory: AgentFactory,
    *,
    requests: Sequence[DecisionRequest],
) -> None:
    """Factory identity、Session分離、合法応答、冪等closeを検証する."""
    if len(requests) < 2:
        raise ValueError("requests must contain at least two session cases")
    spec = factory.spec
    _require(isinstance(spec, AgentSpec), "factory.spec must be AgentSpec")
    _require(factory.spec == spec, "factory.spec must be stable")
    sessions: list[AgentSession] = []
    try:
        for request in requests:
            session = factory.create(request.context)
            _require(isinstance(session, AgentSession), "factory.create must return AgentSession")
            sessions.append(session)
        _require(
            len({id(session) for session in sessions}) == len(sessions),
            "factory.create must isolate sessions",
        )
        for session, request in zip(sessions, requests, strict=True):
            response = session.decide(request)
            _require(
                isinstance(response, DecisionResponse),
                "AgentSession.decide must return DecisionResponse",
            )
            _assert_legal_response(request, response)
    finally:
        close_errors: list[Exception] = []
        for session in sessions:
            try:
                session.close()
                session.close()
            except Exception as error:
                close_errors.append(error)
        if close_errors:
            raise AssertionError("AgentSession.close must be idempotent") from close_errors[0]


def _assert_legal_response(request: DecisionRequest, response: DecisionResponse) -> None:
    option = next(
        (
            item
            for item in request.options
            if item.action_type == response.action_type and item.ability_id == response.ability_id
        ),
        None,
    )
    _require(option is not None, "response action must be one of the requested options")
    option = cast(DecisionOption, option)
    _assert_target(option, response)
    if response.action_type == "speech":
        _require(response.utterance is not None, "speech response must contain an utterance")
        _require(
            response.position in option.legal_positions,
            "speech response must contain a legal position",
        )
        _require(
            response.relation in option.legal_relations,
            "speech response must contain a legal relation",
        )
        _require(
            response.topic_id in option.legal_topic_ids,
            "speech response must identify a legal topic",
        )
        if option.message_max_chars is not None:
            _require(
                len(cast(str, response.utterance)) <= option.message_max_chars,
                "speech response must respect message_max_chars",
            )
        if option.legal_reference_ids:
            _require(
                response.response_to_id in option.legal_reference_ids,
                "speech response must use one of the legal references",
            )
            _require(
                response.evidence_id == response.response_to_id,
                "response speech must use its reference as evidence",
            )
        else:
            _require(
                response.evidence_id is None
                or response.evidence_id in {item.evidence_id for item in option.evidence_options},
                "opening speech must cite legal evidence",
            )
            _require(
                response.response_to_id is None,
                "opening speech response must not contain a reference",
            )
    else:
        _require(response.utterance is None, "non-speech response must not contain an utterance")
        _require(response.position is None, "non-speech response must not contain position")
        _require(response.relation is None, "non-speech response must not contain relation")
        _require(response.topic_id is None, "non-speech response must not contain topic_id")
        _require(
            response.response_to_id is None,
            "non-speech response must not contain a reference",
        )
    if response.action_type == "vote":
        _require(response.reason is not None, "vote response must contain a reason")
        if option.evidence_options:
            _require(
                response.evidence_id in {item.evidence_id for item in option.evidence_options},
                "vote response must use visible evidence",
            )
    else:
        _require(response.reason is None, "non-vote response must not contain a reason")


def _assert_target(option: DecisionOption, response: DecisionResponse) -> None:
    if option.legal_target_ids:
        _require(
            response.target_id in option.legal_target_ids,
            "response target must be one of the legal targets",
        )
    else:
        _require(response.target_id is None, "targetless option must not contain a target")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


__all__ = ["assert_agent_factory_contract"]
