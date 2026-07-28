from http import HTTPStatus
from typing import get_args

import pytest
from pydantic import ValidationError

import werewolf_agent.contracts as contracts_package
from werewolf_agent.contracts import (
    ACTIVE_ADVANCE_JOB_STATUSES,
    ADVANCE_JOB_STATUS_COMPLETED,
    ADVANCE_JOB_STATUS_FAILED,
    ADVANCE_JOB_STATUS_QUEUED,
    ADVANCE_JOB_STATUS_RUNNING,
    ERROR_CONTEXT_HTTP_STATUS,
    ERROR_CONTEXT_LLM_BASE_URL,
    ERROR_CONTEXT_LLM_ERROR_TYPE,
    ERROR_CONTEXT_LLM_MAX_TOKENS,
    ERROR_CONTEXT_LLM_MODEL,
    ERROR_CONTEXT_LLM_PROVIDER,
    ERROR_CONTEXT_LLM_TIMEOUT_SECONDS,
    ERROR_CONTEXT_PROBLEM_TYPE,
    ERROR_CONTEXT_SCHEMA,
    ERROR_SPECS,
    LLM_PROVIDER_ERROR_INVALID_MODELS_RESPONSE,
    LLM_PROVIDER_ERROR_NO_LOADED_MODEL,
    AdvanceJobStatus,
    AppError,
    ErrorCode,
    ErrorEventPayload,
    ErrorSpec,
    GamePhase,
    GamePhaseError,
    GameStatus,
    LlmProviderError,
    ProblemDetails,
    ProblemIssue,
    RoleCount,
    RoleId,
    Winner,
    problem_details_from_error,
    problem_details_from_spec,
)
from werewolf_agent.contracts.errors import problem_type_uri


def test_contracts_package_reexports_public_api() -> None:
    assert contracts_package.AppError is AppError
    assert contracts_package.GamePhaseError is GamePhaseError
    assert contracts_package.ErrorCode is ErrorCode
    assert contracts_package.problem_details_from_error is problem_details_from_error
    assert contracts_package.problem_details_from_spec is problem_details_from_spec
    assert contracts_package.GamePhase is GamePhase
    assert contracts_package.GameStatus is GameStatus
    assert contracts_package.RoleId is RoleId
    assert contracts_package.RoleCount is RoleCount
    assert contracts_package.Winner is Winner


def test_error_codes_are_unique_and_all_have_specs() -> None:
    values = [code.value for code in ErrorCode]

    assert len(values) == len(set(values))
    assert set(ERROR_SPECS) == set(ErrorCode)

    for code, spec in ERROR_SPECS.items():
        assert isinstance(code, ErrorCode)
        assert isinstance(spec, ErrorSpec)
        assert isinstance(spec.status, HTTPStatus)
        assert spec.title
        assert spec.detail
        assert spec.log_level in {"INFO", "WARNING", "ERROR"}


def test_error_specs_classify_expected_user_errors_as_info() -> None:
    assert ERROR_SPECS[ErrorCode.CONFIG_INVALID_VALUE].log_level == "INFO"
    assert ERROR_SPECS[ErrorCode.GAME_INVALID_ACTION].log_level == "INFO"
    assert ERROR_SPECS[ErrorCode.GAME_INVALID_PHASE].log_level == "INFO"
    assert ERROR_SPECS[ErrorCode.RESOURCE_NOT_FOUND].log_level == "INFO"


def test_error_specs_classify_operational_failures_above_info() -> None:
    assert ERROR_SPECS[ErrorCode.API_UNAVAILABLE].log_level == "WARNING"
    assert ERROR_SPECS[ErrorCode.LLM_PROVIDER_UNAVAILABLE].log_level == "WARNING"
    assert ERROR_SPECS[ErrorCode.OBSERVATION_WRITE_FAILED].log_level == "WARNING"
    assert ERROR_SPECS[ErrorCode.INTERNAL_UNEXPECTED].log_level == "ERROR"


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
        "error_message": "Player cannot vote during the night.",
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
        "retryable": False,
        "recovery": "none",
    }


def test_problem_details_helper_from_error_matches_contract_shape() -> None:
    error = AppError(
        "Player cannot vote during the night.",
        code=ErrorCode.GAME_INVALID_ACTION,
    )

    problem = problem_details_from_error(
        error,
        instance="/api/v1/games/game-1/actions",
        trace_id="trace-1",
    )

    assert isinstance(problem, ProblemDetails)
    assert problem.model_dump(mode="json", exclude_none=True) == {
        "type": "tag:werewolf-agent,2026:problem:game.invalid_action",
        "title": ERROR_SPECS[ErrorCode.GAME_INVALID_ACTION].title,
        "status": int(ERROR_SPECS[ErrorCode.GAME_INVALID_ACTION].status),
        "detail": "Player cannot vote during the night.",
        "instance": "/api/v1/games/game-1/actions",
        "code": "game.invalid_action",
        "trace_id": "trace-1",
        "retryable": False,
        "recovery": "none",
    }


def test_problem_details_helper_from_spec_allows_response_overrides() -> None:
    issue = ProblemIssue(code="required", detail="This field is required.", pointer="/name")

    problem = problem_details_from_spec(
        ErrorCode.REQUEST_VALIDATION_FAILED,
        instance="/api/v1/games",
        trace_id="trace-2",
        status_code=422,
        detail="Custom validation detail.",
        errors=[issue],
    )

    assert problem.model_dump(mode="json", exclude_none=True) == {
        "type": "tag:werewolf-agent,2026:problem:request.validation_failed",
        "title": ERROR_SPECS[ErrorCode.REQUEST_VALIDATION_FAILED].title,
        "status": 422,
        "detail": "Custom validation detail.",
        "instance": "/api/v1/games",
        "code": "request.validation_failed",
        "trace_id": "trace-2",
        "errors": [{"code": "required", "detail": "This field is required.", "pointer": "/name"}],
        "retryable": False,
        "recovery": "none",
    }


def test_error_context_keys_and_provider_diagnostics_are_reexported() -> None:
    assert ERROR_CONTEXT_LLM_ERROR_TYPE == "llm_error_type"
    assert ERROR_CONTEXT_LLM_PROVIDER == "llm_provider"
    assert ERROR_CONTEXT_LLM_MODEL == "llm_model"
    assert ERROR_CONTEXT_LLM_BASE_URL == "llm_base_url"
    assert ERROR_CONTEXT_LLM_TIMEOUT_SECONDS == "llm_timeout_seconds"
    assert ERROR_CONTEXT_LLM_MAX_TOKENS == "llm_max_tokens"
    assert ERROR_CONTEXT_HTTP_STATUS == "http_status"
    assert ERROR_CONTEXT_PROBLEM_TYPE == "problem_type"
    assert ERROR_CONTEXT_SCHEMA == "schema"
    assert LLM_PROVIDER_ERROR_INVALID_MODELS_RESPONSE == "InvalidModelsResponse"
    assert LLM_PROVIDER_ERROR_NO_LOADED_MODEL == "NoLoadedModel"


def test_advance_job_status_constants_match_public_status_contract() -> None:
    assert set(get_args(AdvanceJobStatus)) == {
        ADVANCE_JOB_STATUS_QUEUED,
        ADVANCE_JOB_STATUS_RUNNING,
        ADVANCE_JOB_STATUS_COMPLETED,
        ADVANCE_JOB_STATUS_FAILED,
    }
    assert (
        frozenset({ADVANCE_JOB_STATUS_QUEUED, ADVANCE_JOB_STATUS_RUNNING})
        == ACTIVE_ADVANCE_JOB_STATUSES
    )


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
