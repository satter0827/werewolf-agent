"""Security and transaction boundaries for the asynchronous worker."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import SecretStr

from werewolf_agent.adapters.usecase_bridge import build_worker_llm_provider_config
from werewolf_agent.configuration import AppSettings
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import ProblemDetails
from werewolf_agent.interfaces.worker import service


@dataclass
class _Result:
    row: dict[str, Any] | None = None
    rowcount: int = 1

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


class _Connection:
    def __init__(self, rows: list[dict[str, Any] | None]) -> None:
        self._rows = iter(rows)
        self.transaction_count = 0

    def execute(self, _query: str, _params: object = None) -> _Result:
        return _Result(next(self._rows))

    def transaction(self) -> Any:
        self.transaction_count += 1
        return nullcontext()


@pytest.mark.parametrize(
    ("requested_mode", "is_anonymous", "expected"),
    [("fake", True, "fake"), ("fake", False, "fake"), ("paid", False, "paid")],
)
def test_creation_llm_mode_is_fixed_at_acceptance_and_reverified(
    requested_mode: str,
    is_anonymous: bool,
    expected: str,
) -> None:
    connection = _Connection([{"is_anonymous": is_anonymous}])

    result = service._verified_creation_llm_mode(
        connection,
        owner_user_id="user-1",
        requested_mode=requested_mode,
    )

    assert result == expected


def test_creation_llm_mode_rejects_an_unknown_auth_user() -> None:
    connection = _Connection([None])

    with pytest.raises(AppError) as captured:
        service._verified_creation_llm_mode(
            connection,
            owner_user_id="missing-user",
            requested_mode="fake",
        )

    assert captured.value.code is ErrorCode.AUTHENTICATION_REQUIRED


def test_paid_creation_is_rejected_if_membership_is_no_longer_valid() -> None:
    connection = _Connection([{"is_anonymous": True}])

    with pytest.raises(AppError) as captured:
        service._verified_creation_llm_mode(
            connection,
            owner_user_id="guest-user",
            requested_mode="paid",
        )

    assert captured.value.code is ErrorCode.AUTHORIZATION_FAILED


def test_fake_game_cannot_inherit_the_paid_provider_or_secret() -> None:
    settings = AppSettings.model_validate(
        {
            "llm_provider": "openai",
            "model": "untrusted-default",
            "worker_paid_llm_provider": "openai",
            "worker_paid_llm_model": "paid-model",
            "openai_api_key": SecretStr("paid-secret"),
        }
    )

    config = build_worker_llm_provider_config("fake", settings)

    assert config.provider == "fake"
    assert config.model == "fake-list-llm"
    assert config.base_url == ""
    assert config.api_key == ""


def test_paid_game_uses_worker_only_provider_configuration() -> None:
    settings = AppSettings.model_validate(
        {
            "worker_paid_llm_provider": "openai",
            "worker_paid_llm_model": "paid-model",
            "worker_paid_llm_base_url": "https://llm.example.test/v1",
            "openai_api_key": SecretStr("paid-secret"),
        }
    )

    config = build_worker_llm_provider_config("paid", settings)

    assert config.provider == "openai"
    assert config.model == "paid-model"
    assert config.base_url == "https://llm.example.test/v1"
    assert config.api_key == "paid-secret"


def test_advance_revalidates_participant_access_at_worker_execution() -> None:
    connection = _Connection([None])
    request = {
        "request_id": "operation-1",
        "operation_type": "advance_game",
        "owner_user_id": "removed-user",
        "game_id": "game-1",
        "expected_version": 1,
    }

    with pytest.raises(AppError) as captured:
        service._advance_game(
            connection,
            AppSettings.model_validate({}),
            request,
        )

    assert captured.value.code is ErrorCode.AUTHORIZATION_FAILED


def test_failed_command_is_rolled_back_before_safe_failure_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection([])
    request = {
        "request_id": "operation-1",
        "operation_type": "advance_game",
        "owner_user_id": "user-1",
        "attempt_count": 1,
        "worker_id": "worker-1",
    }
    recorded: list[ProblemDetails] = []

    def fail_execute(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("db_dsn=postgresql://secret")

    monkeypatch.setattr(service, "_execute_request", fail_execute)
    monkeypatch.setattr(
        service,
        "_fail_request",
        lambda _connection, _request, problem: recorded.append(problem),
    )

    service._process_request(
        connection,
        AppSettings.model_validate({}),
        request,
    )

    assert connection.transaction_count == 2
    assert len(recorded) == 1
    problem = recorded[0]
    assert problem.code == ErrorCode.INTERNAL_UNEXPECTED
    assert "postgresql" not in problem.detail
