from types import SimpleNamespace
from typing import Any

import psycopg
import pytest

from werewolf_agent.adapters.supabase import repository
from werewolf_agent.adapters.supabase.worker_store import SupabaseWorkerStore
from werewolf_agent.contracts import AppError, ErrorCode, GameNotFoundError
from werewolf_agent.settings import AppSettings
from werewolf_agent.worker import service as worker_service


def test_worker_database_adapter_hides_driver_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_connect(*_args: object, **_kwargs: object) -> None:
        raise psycopg.OperationalError("private connection detail")

    monkeypatch.setattr(repository.psycopg, "connect", fail_connect)

    with pytest.raises(repository.SupabaseDatabaseUnavailableError) as error:
        repository.connect_worker_database("private-dsn")

    assert str(error.value) == ""


def test_worker_retries_after_transient_database_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    attempts = iter(
        [
            worker_service.SupabaseDatabaseUnavailableError(),
            KeyboardInterrupt(),
        ]
    )

    def process(_settings: AppSettings) -> int:
        raise next(attempts)

    monkeypatch.setattr(worker_service, "process_worker_batch", process)
    monkeypatch.setattr(worker_service.time, "sleep", sleeps.append)

    settings = AppSettings(_env_file=None)
    with pytest.raises(KeyboardInterrupt):
        worker_service.run_worker_forever(settings)

    assert sleeps == [settings.supabase_worker_poll_interval_seconds]


def test_worker_rolls_back_business_savepoint_before_recording_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    connection = TransactionRecordingConnection(events)

    def fail_execution(*_args: object) -> None:
        events.append("execute")
        raise RuntimeError("boom")

    monkeypatch.setattr(worker_service, "_execute_request", fail_execution)
    store = SimpleNamespace(fail_request=lambda *_args: events.append("failed"))

    worker_service._process_request(
        connection,
        store,
        AppSettings(_env_file=None),
        {"request_id": "operation-1", "operation_type": "advance_game"},
    )

    assert events == ["enter", "execute", "rollback", "enter", "failed", "commit"]


def test_worker_claim_recovers_expired_running_operations() -> None:
    connection = RecordingConnection()

    SupabaseWorkerStore(connection).claim_request(worker_id="worker-1", claim_seconds=30)

    claim_sql = connection.calls[0][0].lower()
    assert "status = 'queued'" in claim_sql
    assert "status = 'running'" in claim_sql
    assert "claimed_until <" in claim_sql


def test_worker_completion_is_fenced_by_claim_attempt_and_worker() -> None:
    connection = RecordingConnection()
    request = {
        "request_id": "operation-1",
        "attempt_count": 3,
        "worker_id": "worker-a",
        "operation_type": "advance_game",
    }

    SupabaseWorkerStore(connection).complete_request(
        request,
        {"game_id": "game-1"},
    )

    statement, parameters = connection.calls[0]
    assert "attempt_count = %s" in statement
    assert "worker_id = %s" in statement
    assert parameters[-2:] == (3, "worker-a")


def test_worker_problem_preserves_safe_application_status() -> None:
    conflict = worker_service._problem_from_exception(
        AppError("状態が更新されています。", code=ErrorCode.GAME_INVALID_PHASE)
    )
    missing = worker_service._problem_from_exception(GameNotFoundError("private detail"))
    unexpected = worker_service._problem_from_exception(RuntimeError("secret detail"))

    assert conflict.status == 409
    assert conflict.code == ErrorCode.GAME_INVALID_PHASE.value
    assert conflict.detail == "状態が更新されています。"
    assert missing.status == 404
    assert "private detail" not in missing.model_dump_json()
    assert unexpected.status == 500
    assert "secret detail" not in unexpected.model_dump_json()


def test_worker_deletes_reveal_view_when_reveal_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = RecordingConnection()
    service = FakeWorkerService()
    settings = AppSettings(_env_file=None, reveal_api_enabled=False)

    monkeypatch.setattr(worker_service, "_service", lambda *_args, **_kwargs: service)
    monkeypatch.setattr(worker_service, "_current_game_version", lambda *_args: 1)
    monkeypatch.setattr(
        worker_service.application_handlers,
        "get_player_observation",
        lambda *_args, **_kwargs: SimpleNamespace(observation={"visible": True}),
    )

    worker_service._materialize_private_views(
        connection,
        SupabaseWorkerStore(connection),
        settings,
        "00000000-0000-0000-0000-000000000001",
    )

    statements = [sql.lower() for sql, _params in connection.calls]
    assert any("delete from private.game_reveals" in sql for sql in statements)
    assert not any("insert into private.game_reveals" in sql for sql in statements)
    assert service.reveal_called is False
    observation_call = next(
        params for sql, params in connection.calls if "game_player_observations" in sql
    )
    assert observation_call[3] == 1


class FakeWorkerService:
    def __init__(self) -> None:
        self.reveal_called = False

    def get_game(self, query: object) -> SimpleNamespace:
        _ = query
        return SimpleNamespace(state={"version": 7})

    def get_game_reveal(self, query: object) -> SimpleNamespace:
        _ = query
        self.reveal_called = True
        return SimpleNamespace()

    def get_player_observation(self, query: object) -> SimpleNamespace:
        _ = query
        return SimpleNamespace(observation={"visible": True})


class RecordingConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> "RecordingResult":
        self.calls.append((sql, params))
        if "from public.game_participants" in sql:
            return RecordingResult(
                rows=[
                    {"user_id": "user-1", "player_id": "player-1"},
                    {"user_id": "user-owner", "player_id": "observer"},
                ]
            )
        return RecordingResult()


class TransactionRecordingConnection:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def transaction(self) -> "RecordingTransaction":
        return RecordingTransaction(self._events)


class RecordingTransaction:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def __enter__(self) -> None:
        self._events.append("enter")

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object,
    ) -> bool:
        del exception, traceback
        self._events.append("rollback" if exception_type is not None else "commit")
        return False


class RecordingResult:
    def __init__(self, *, rows: list[dict[str, str]] | None = None) -> None:
        self._rows = rows or []

    def fetchall(self) -> list[dict[str, str]]:
        return self._rows

    def fetchone(self) -> dict[str, str] | None:
        return self._rows[0] if self._rows else None
