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
        _require(response.message is not None, "speech response must contain a message")
        _require(
            response.speech_act in {"question", "answer", "support", "challenge", "revise"},
            "speech response must contain a supported speech_act",
        )
        if option.legal_reference_ids:
            _require(
                response.speech_act in {"answer", "support", "challenge", "revise"},
                "response speech must advance the referenced exchange",
            )
        _require(
            response.subject_id in option.legal_subject_ids,
            "speech response must identify a legal subject",
        )
        if option.message_max_chars is not None:
            _require(
                len(cast(str, response.message)) <= option.message_max_chars,
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
                response.speech_act != "answer",
                "opening speech must not use answer",
            )
            _require(
                response.speech_act == "question" or response.evidence_id is not None,
                "non-question opening speech must cite evidence",
            )
            _require(
                response.evidence_id is None or response.evidence_id in option.legal_evidence_ids,
                "opening speech must cite legal evidence",
            )
            _require(
                response.response_to_id is None,
                "opening speech response must not contain a reference",
            )
    else:
        _require(response.message is None, "non-speech response must not contain a message")
        _require(response.speech_act is None, "non-speech response must not contain speech_act")
        _require(response.subject_id is None, "non-speech response must not contain subject_id")
        _require(
            response.response_to_id is None,
            "non-speech response must not contain a reference",
        )
    if response.action_type == "vote":
        _require(response.reason is not None, "vote response must contain a reason")
        if option.legal_evidence_ids:
            _require(
                response.evidence_id in option.legal_evidence_ids,
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
