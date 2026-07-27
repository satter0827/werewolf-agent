from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.adapters.supabase.setup_repository import SupabaseSetupRepository
from werewolf_agent.application.errors import AppError, ErrorCode

OWNER_ID = "11111111-1111-1111-1111-111111111111"
SETUP_ID = "22222222-2222-2222-2222-222222222222"


class _Cursor:
    def __init__(self, *, one: Any = None, all_rows: list[Any] | None = None) -> None:
        self._one = one
        self._all = all_rows or []

    def fetchone(self) -> Any:
        return self._one

    def fetchall(self) -> list[Any]:
        return self._all


class _Connection:
    def __init__(self, cursors: list[_Cursor]) -> None:
        self._cursors = list(cursors)
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, query: str, parameters: tuple[Any, ...]) -> _Cursor:
        self.calls.append((query, parameters))
        return self._cursors.pop(0)


def test_setup_read_is_always_scoped_to_owner() -> None:
    connection = _Connection([_Cursor(one=None)])
    repository = SupabaseSetupRepository(connection)

    assert repository.get(SETUP_ID, owner_user_id=OWNER_ID) is None

    query, parameters = connection.calls[0]
    assert "s.owner_user_id = %s" in query
    assert parameters[0] == UUID(SETUP_ID)
    assert parameters[1] == UUID(OWNER_ID)


def test_revision_conflict_is_detected_while_parent_is_locked() -> None:
    connection = _Connection(
        [
            _Cursor(one={"setup_id": UUID(SETUP_ID)}),
            _Cursor(one={"latest_revision": 2}),
        ]
    )
    repository = SupabaseSetupRepository(connection)
    document = build_setup_catalog().require_document("standard_6")

    with pytest.raises(AppError) as raised:
        repository.add_revision(
            SETUP_ID,
            owner_user_id=OWNER_ID,
            expected_revision=1,
            document=document,
            setup_checksum="a" * 64,
            mechanics_checksum="b" * 64,
        )

    assert raised.value.code is ErrorCode.SETUP_REVISION_CONFLICT
    assert "for update" in connection.calls[0][0].lower()
    assert connection.calls[0][1] == (UUID(SETUP_ID), UUID(OWNER_ID))
