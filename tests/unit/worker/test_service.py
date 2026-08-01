"""Security and transaction boundaries for the asynchronous worker."""

from __future__ import annotations

import logging
from contextlib import nullcontext
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel, SecretStr

from werewolf_agent.adapters.application_bridge import build_worker_llm_provider_config
from werewolf_agent.adapters.supabase.worker_store import SupabaseWorkerStore
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import GameResponse, ProblemDetails
from werewolf_agent.settings import AppSettings
from werewolf_agent.worker import service
from werewolf_agent.worker.composition import create_core_worker_dependencies

WORKER_DEPENDENCIES = create_core_worker_dependencies()


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

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _Pool:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection

    def connection(self) -> _Connection:
        return self._connection


class _ApplicationResult(BaseModel):
    game_id: str
    state: dict[str, Any]


def test_wire_mapping_excludes_internal_story_theme_fields() -> None:
    theme = {
        "id": "village",
        "name": "Village",
        "premise": "Find the threat.",
        "role_names": {},
        "role_objectives": {},
        "faction_names": {},
        "ability_names": {},
        "action_names": {},
        "phase_names": {},
        "summary": "Internal setup summary",
        "narration": {"game_started": ["Internal narration"]},
    }
    source = _ApplicationResult(
        game_id="game-1",
        state={
            "game_id": "game-1",
            "status": "running",
            "phase": "day_discussion",
            "day": 1,
            "version": 1,
            "theme": theme,
            "players": [],
            "alive_player_ids": [],
            "eliminated_player_ids": [],
            "summary": {},
        },
    )

    response = service._wire_model(GameResponse, source)

    assert response.state.theme is not None
    assert response.state.theme.model_dump()["id"] == "village"
    assert "summary" not in response.state.theme.model_dump()
    assert "narration" not in response.state.theme.model_dump()


def test_worker_archives_exhausted_message_without_executing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection([])
    request = {
        "request_id": "operation-1",
        "operation_type": "advance_game",
        "owner_user_id": "user-1",
        "attempt_count": 4,
        "worker_id": "worker-1",
        "queue_message_id": 42,
    }
    failures: list[ProblemDetails] = []

    class Store:
        def __init__(self, _connection: object) -> None:
            pass

        def claim_requests(self, **_kwargs: object) -> list[dict[str, Any]]:
            return [request]

        def fail_request(self, _request: object, problem: ProblemDetails) -> None:
            failures.append(problem)

    monkeypatch.setattr(service, "SupabaseWorkerStore", Store)
    monkeypatch.setattr(
        service,
        "_process_request",
        lambda *_args: pytest.fail("exhausted operation must not execute"),
    )

    processed = service.process_worker_batch(
        AppSettings(
            _env_file=None,
            supabase_worker_db_dsn=SecretStr("postgresql://local"),
        ),
        dependencies=WORKER_DEPENDENCIES,
        pool=_Pool(connection),
    )

    assert processed == 1
    assert failures[0].code == ErrorCode.OPERATION_RETRY_EXHAUSTED.value


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

    result = SupabaseWorkerStore(connection).verify_creation_llm_mode(
        owner_user_id="user-1",
        requested_mode=requested_mode,
    )

    assert result == expected


def test_creation_llm_mode_rejects_an_unknown_auth_user() -> None:
    connection = _Connection([None])

    with pytest.raises(AppError) as captured:
        SupabaseWorkerStore(connection).verify_creation_llm_mode(
            owner_user_id="missing-user",
            requested_mode="fake",
        )

    assert captured.value.code is ErrorCode.AUTHENTICATION_REQUIRED


def test_paid_creation_is_rejected_if_membership_is_no_longer_valid() -> None:
    connection = _Connection([{"is_anonymous": True}])

    with pytest.raises(AppError) as captured:
        SupabaseWorkerStore(connection).verify_creation_llm_mode(
            owner_user_id="guest-user",
            requested_mode="paid",
        )

    assert captured.value.code is ErrorCode.AUTHORIZATION_FAILED


def test_fake_game_cannot_inherit_the_paid_provider_or_secret() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider="openai",
        model="untrusted-default",
        worker_paid_llm_provider="openai",
        worker_paid_llm_model="paid-model",
        openai_api_key=SecretStr("paid-secret"),
    )

    config = build_worker_llm_provider_config("fake", settings)

    assert config.provider == "fake"
    assert config.model == "fake-list-chat-model"
    assert config.base_url == ""
    assert config.api_key == ""


def test_paid_game_uses_worker_only_provider_configuration() -> None:
    settings = AppSettings(
        _env_file=None,
        worker_paid_llm_provider="openai",
        worker_paid_llm_model="paid-model",
        worker_paid_llm_base_url="https://llm.example.test/v1",
        openai_api_key=SecretStr("paid-secret"),
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
        service._execute_advance_request(
            _Pool(connection),
            AppSettings(_env_file=None),
            WORKER_DEPENDENCIES,
            request,
        )

    assert captured.value.code is ErrorCode.AUTHORIZATION_FAILED


def test_paid_advance_is_fail_closed_before_runtime_when_switch_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection([])

    class Application:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def prepare_advance(self, *_args: object) -> object:
            return object()

    class Store:
        def __init__(self, _connection: object) -> None:
            pass

        def game_llm_mode(self, _game_id: str) -> str:
            return "paid"

    monkeypatch.setattr(service, "_service", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(service, "GameApplication", Application)
    monkeypatch.setattr(service, "SupabaseWorkerStore", Store)
    monkeypatch.setattr(
        service,
        "drive_prepared_game",
        lambda *_args, **_kwargs: pytest.fail("paid runtime must not start"),
    )

    with pytest.raises(AppError, match="disabled") as captured:
        service._execute_advance_request(
            _Pool(connection),
            AppSettings(_env_file=None),
            WORKER_DEPENDENCIES,
            {
                "request_id": "operation-1",
                "owner_user_id": "user-1",
                "game_id": "game-1",
                "expected_version": 1,
            },
        )

    assert captured.value.code is ErrorCode.LLM_PROVIDER_UNAVAILABLE
    assert captured.value.retryable is False


def test_failed_command_is_rolled_back_before_safe_failure_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection([])
    request = {
        "request_id": "operation-1",
        "operation_type": "create_game",
        "owner_user_id": "user-1",
        "attempt_count": 1,
        "worker_id": "worker-1",
    }
    recorded: list[ProblemDetails] = []

    def fail_execute(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("db_dsn=postgresql://secret")

    monkeypatch.setattr(service, "_execute_request", fail_execute)
    store = SimpleNamespace(fail_request=lambda _request, problem: recorded.append(problem))
    monkeypatch.setattr(service, "SupabaseWorkerStore", lambda _connection: store)

    service._process_request(
        _Pool(connection),
        AppSettings(_env_file=None),
        WORKER_DEPENDENCIES,
        request,
    )

    assert connection.transaction_count == 2
    assert len(recorded) == 1
    problem = recorded[0]
    assert problem.code == ErrorCode.INTERNAL_UNEXPECTED
    assert "postgresql" not in problem.detail


def test_retry_logs_state_change_once_and_each_attempt_at_debug(
    monkeypatch: pytest.MonkeyPatch,
    caplog,
) -> None:
    connection = _Connection([])
    request = {
        "request_id": "operation-1",
        "operation_type": "create_game",
        "owner_user_id": "user-1",
        "attempt_count": 1,
        "worker_id": "worker-1",
    }
    retried: list[ProblemDetails] = []

    def fail_execute(*_args: object, **_kwargs: object) -> None:
        raise AppError(code=ErrorCode.API_UNAVAILABLE)

    monkeypatch.setattr(service, "_execute_request", fail_execute)
    store = SimpleNamespace(retry_request=lambda _request, problem: retried.append(problem))
    monkeypatch.setattr(service, "SupabaseWorkerStore", lambda _connection: store)

    with caplog.at_level(logging.DEBUG, logger=service.logger.name):
        service._process_request(
            _Pool(connection),
            AppSettings(_env_file=None, supabase_worker_max_attempts=3),
            WORKER_DEPENDENCIES,
            request,
        )

    assert len(retried) == 1
    records = [record for record in caplog.records if record.name == service.logger.name]
    assert [record.levelno for record in records] == [logging.WARNING, logging.DEBUG]
    assert [record.event_action for record in records] == [
        service.LOG_WORKER_REQUEST_RETRY_STARTED,
        service.LOG_WORKER_REQUEST_RETRY_SCHEDULED,
    ]
