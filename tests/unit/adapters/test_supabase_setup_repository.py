from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.adapters.supabase.setup_repository import SupabaseSetupRepository
from werewolf_agent.application.errors import AppError, ErrorCode
from werewolf_agent.setup import SETUP_SCHEMA_VERSION

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
    assert parameters[2] == SETUP_SCHEMA_VERSION


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
            max_revisions=100,
        )

    assert raised.value.code is ErrorCode.SETUP_REVISION_CONFLICT
    assert "for update" in connection.calls[0][0].lower()
    assert connection.calls[0][1] == (
        UUID(SETUP_ID),
        UUID(OWNER_ID),
        SETUP_SCHEMA_VERSION,
    )


def test_revision_list_is_bounded_by_limit_and_offset() -> None:
    connection = _Connection([_Cursor(all_rows=[])])

    assert (
        SupabaseSetupRepository(connection).list_revisions(
            SETUP_ID,
            owner_user_id=OWNER_ID,
            limit=21,
            offset=40,
        )
        == []
    )

    query, parameters = connection.calls[0]
    assert "limit %s offset %s" in query.lower()
    assert parameters == (
        UUID(SETUP_ID),
        UUID(OWNER_ID),
        SETUP_SCHEMA_VERSION,
        21,
        40,
    )


def test_setup_list_is_bounded_by_limit_and_offset() -> None:
    connection = _Connection([_Cursor(all_rows=[])])

    assert (
        SupabaseSetupRepository(connection).list_setups(
            owner_user_id=OWNER_ID,
            limit=21,
            offset=40,
        )
        == []
    )

    query, parameters = connection.calls[0]
    assert "limit %s offset %s" in query.lower()
    assert parameters == (SETUP_SCHEMA_VERSION, UUID(OWNER_ID), 21, 40)


def test_setup_limit_is_checked_under_owner_lock_before_insert() -> None:
    connection = _Connection(
        [
            _Cursor(),
            _Cursor(one={"setup_count": 2}),
        ]
    )
    document = build_setup_catalog().require_document("standard_6")

    with pytest.raises(AppError) as raised:
        SupabaseSetupRepository(connection).create(
            owner_user_id=OWNER_ID,
            display_name="実験設定",
            document=document,
            setup_checksum="a" * 64,
            mechanics_checksum="b" * 64,
            max_setups=2,
        )

    assert raised.value.code is ErrorCode.SETUP_LIMIT_REACHED
    assert "pg_advisory_xact_lock" in connection.calls[0][0]
    assert "count(*)" in connection.calls[1][0].lower()
    assert connection.calls[1][1] == (UUID(OWNER_ID), SETUP_SCHEMA_VERSION)
    assert len(connection.calls) == 2


def test_revision_limit_is_checked_before_insert() -> None:
    connection = _Connection(
        [
            _Cursor(one={"setup_id": UUID(SETUP_ID)}),
            _Cursor(one={"latest_revision": 2}),
        ]
    )
    document = build_setup_catalog().require_document("standard_6")

    with pytest.raises(AppError) as raised:
        SupabaseSetupRepository(connection).add_revision(
            SETUP_ID,
            owner_user_id=OWNER_ID,
            expected_revision=2,
            document=document,
            setup_checksum="a" * 64,
            mechanics_checksum="b" * 64,
            max_revisions=2,
        )

    assert raised.value.code is ErrorCode.SETUP_REVISION_LIMIT_REACHED
    assert len(connection.calls) == 2
