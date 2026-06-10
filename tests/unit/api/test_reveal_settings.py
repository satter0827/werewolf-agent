from types import SimpleNamespace
from typing import Any

import pytest

from werewolf_agent.api.supabase.worker import service as worker_service
from werewolf_agent.commons.configuration import AppSettings


def test_worker_deletes_reveal_view_when_reveal_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = RecordingConnection()
    service = FakeWorkerService()
    settings = AppSettings(_env_file=None, reveal_api_enabled=False)

    monkeypatch.setattr(worker_service, "_service", lambda *_args, **_kwargs: service)

    worker_service._materialize_private_views(connection, settings, "game-1")

    statements = [sql.lower() for sql, _params in connection.calls]
    assert any("delete from public.game_reveals" in sql for sql in statements)
    assert not any("insert into public.game_reveals" in sql for sql in statements)
    assert service.reveal_called is False
    observation_call = next(
        params for sql, params in connection.calls if "game_player_observations" in sql
    )
    assert observation_call[3] == 7


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


class RecordingResult:
    def __init__(self, *, rows: list[dict[str, str]] | None = None) -> None:
        self._rows = rows or []

    def fetchall(self) -> list[dict[str, str]]:
        return self._rows
