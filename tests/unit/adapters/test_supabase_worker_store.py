"""Supabase worker storeのprivate replay境界を検証する。"""

from __future__ import annotations

from typing import Any

import pytest

from werewolf_agent.adapters.supabase import worker_store
from werewolf_agent.adapters.supabase.worker_store import SupabaseWorkerStore


class _Result:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _Result:
        self.calls.append((sql, params))
        if "from private.game_snapshots" in sql:
            return _Result(
                [
                    {
                        "seed": 991,
                        "config": {},
                        "private_state": {"players": {"p1": {"id": "p1", "name": "葵"}}},
                    }
                ]
            )
        return _Result()


def test_create_replay_reads_runtime_seed_from_private_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """公開stateにseedがなくてもprivate replayの決定性を維持する。"""
    connection = _Connection()
    monkeypatch.setattr(worker_store, "jsonb", lambda value: value)
    request = {
        "request_id": "operation-1",
        "operation_type": "create_game",
        "owner_user_id": "user-1",
        "request_payload": {"seed": 17},
    }

    SupabaseWorkerStore(connection).record_accepted_command(
        request,
        {"game_id": "game-1", "state": {"version": 1}},
    )

    snapshot_sql = next(sql for sql, _params in connection.calls if "game_snapshots" in sql)
    assert "select seed, config, private_state" in snapshot_sql
    accepted_params = next(
        params for sql, params in connection.calls if "insert into private.accepted_commands" in sql
    )
    payload = accepted_params[5]
    assert payload["request"]["seed"] == 991
    assert payload["replay"]["seed"] == 991
