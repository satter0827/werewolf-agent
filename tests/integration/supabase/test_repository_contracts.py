"""Supabase repositoryへapplication共通契約を適用する。"""

from __future__ import annotations

import os
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from tests.contracts.repository_contracts import (
    assert_game_repository_contract,
    assert_setup_repository_contract,
)

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.adapters.supabase.repository import SupabaseGameRepository
from werewolf_agent.adapters.supabase.setup_repository import SupabaseSetupRepository

pytestmark = [pytest.mark.supabase, pytest.mark.serial]

INSTANCE_ID = UUID(int=0)


def _insert_user(connection: psycopg.Connection, user_id: UUID) -> None:
    connection.execute(
        """
        insert into auth.users (instance_id, id, aud, role)
        values (%s, %s, 'authenticated', 'authenticated')
        """,
        (INSTANCE_ID, user_id),
    )


def test_supabase_game_repository_satisfies_shared_contract() -> None:
    owner_id = uuid4()
    game_id = uuid4()
    with psycopg.connect(
        os.environ["WEREWOLF_SUPABASE_DB_DSN"],
        row_factory=dict_row,
    ) as connection:
        _insert_user(connection, owner_id)
        assert_game_repository_contract(
            SupabaseGameRepository(connection, owner_user_id=str(owner_id)),
            game_id=game_id,
        )
        connection.rollback()


def test_supabase_setup_repository_satisfies_shared_contract() -> None:
    owner_id = uuid4()
    other_id = uuid4()
    with psycopg.connect(
        os.environ["WEREWOLF_SUPABASE_DB_DSN"],
        row_factory=dict_row,
    ) as connection:
        _insert_user(connection, owner_id)
        _insert_user(connection, other_id)
        assert_setup_repository_contract(
            SupabaseSetupRepository(connection),
            owner_user_id=str(owner_id),
            other_user_id=str(other_id),
            document=build_setup_catalog().require_document("standard_6"),
        )
        connection.rollback()
