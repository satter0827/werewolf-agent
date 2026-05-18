from http import HTTPStatus

import pytest
from pydantic import ValidationError

import werewolf_agent.commons as errors_package
from werewolf_agent.commons import (
    ERROR_SPECS,
    AppError,
    ErrorCode,
    GamePhaseError,
    LlmProviderError,
    problem_type_uri,
)
from werewolf_agent.commons.schemas import ErrorEventPayload, ProblemDetails, ProblemIssue


def test_errors_package_reexports_public_api() -> None:
    assert errors_package.AppError is AppError
    assert errors_package.ErrorCode is ErrorCode
    assert errors_package.GamePhaseError is GamePhaseError


def test_error_codes_are_unique_and_all_have_specs() -> None:
    values = [code.value for code in ErrorCode]

    assert len(values) == len(set(values))
    assert set(ERROR_SPECS) == set(ErrorCode)

    for code, spec in ERROR_SPECS.items():
        assert isinstance(code, ErrorCode)
        assert isinstance(spec.status, HTTPStatus)
        assert spec.title
        assert spec.detail


def test_problem_type_uri_uses_stable_tag_scheme() -> None:
    assert (
        problem_type_uri(ErrorCode.GAME_INVALID_ACTION)
        == "tag:werewolf-agent,2026:problem:game.invalid_action"
    )


def test_app_error_uses_default_spec_metadata() -> None:
    error = GamePhaseError()

    assert error.code == ErrorCode.GAME_INVALID_PHASE
    assert error.detail == ERROR_SPECS[ErrorCode.GAME_INVALID_PHASE].detail
    assert error.retryable is False


def test_app_error_allows_safe_detail_and_log_extra() -> None:
    error = AppError(
        "Player cannot vote during the night.",
        code=ErrorCode.GAME_INVALID_ACTION,
        context={"player_id": "player-1"},
    )

    assert str(error) == "Player cannot vote during the night."
    assert error.log_extra(trace_id="trace-1") == {
        "error_code": "game.invalid_action",
        "retryable": False,
        "trace_id": "trace-1",
        "error_context": {"player_id": "player-1"},
    }


def test_retryable_defaults_come_from_error_spec() -> None:
    error = LlmProviderError()

    assert error.retryable is True
    assert error.log_extra()["error_code"] == "llm.provider_unavailable"


def test_problem_details_contract_dumps_without_none_fields() -> None:
    problem = ProblemDetails(
        type="tag:werewolf-agent,2026:problem:game.invalid_action",
        title="Invalid Game Action",
        status=422,
        detail="The requested game action is not valid.",
        instance="/api/games/1/actions/",
        code="game.invalid_action",
    )

    assert problem.model_dump(mode="json", exclude_none=True) == {
        "type": "tag:werewolf-agent,2026:problem:game.invalid_action",
        "title": "Invalid Game Action",
        "status": 422,
        "detail": "The requested game action is not valid.",
        "instance": "/api/games/1/actions/",
        "code": "game.invalid_action",
    }


def test_problem_details_contract_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ProblemDetails(
            type="tag:werewolf-agent,2026:problem:game.invalid_action",
            title="Invalid Game Action",
            status=422,
            detail="The requested game action is not valid.",
            instance="/api/games/1/actions/",
            code="game.invalid_action",
            debug="secret",
        )


def test_problem_details_contract_accepts_validation_issues() -> None:
    problem = ProblemDetails(
        type="tag:werewolf-agent,2026:problem:request.validation_failed",
        title="Request Validation Failed",
        status=400,
        detail="The request body or parameters failed validation.",
        instance="/api/games/",
        code="request.validation_failed",
        errors=[ProblemIssue(code="required", detail="This field is required.", pointer="/name")],
    )

    assert problem.model_dump(mode="json", exclude_none=True)["errors"] == [
        {"code": "required", "detail": "This field is required.", "pointer": "/name"}
    ]


def test_error_event_payload_contract_dumps_without_empty_context() -> None:
    payload = ErrorEventPayload(
        code="observation.write_failed",
        detail="Could not write event.",
        retryable=True,
    )

    assert payload.model_dump(mode="json", exclude_none=True) == {
        "code": "observation.write_failed",
        "detail": "Could not write event.",
        "retryable": True,
    }
