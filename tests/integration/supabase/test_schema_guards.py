"""ローカルDBへ適用された安全性制約を検査する。"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.errors import InsufficientPrivilege, LockNotAvailable
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from werewolf_agent.adapters.application_bridge import (
    build_game_application_config,
    build_setup_catalog,
)
from werewolf_agent.adapters.supabase.worker_store import SupabaseWorkerStore
from werewolf_agent.application.setup_facade import SetupApplication
from werewolf_agent.settings import AppSettings
from werewolf_agent.worker.service import process_worker_batch

pytestmark = [pytest.mark.supabase]

INSTANCE_ID = UUID(int=0)


def _insert_user(connection: psycopg.Connection, user_id: UUID) -> None:
    connection.execute(
        """
        insert into auth.users (instance_id, id, aud, role)
        values (%s, %s, 'authenticated', 'authenticated')
        """,
        (INSTANCE_ID, user_id),
    )


def _assume_authenticated_user(connection: psycopg.Connection, user_id: UUID) -> None:
    connection.execute("set local role authenticated")
    connection.execute(
        "select set_config('request.jwt.claim.sub', %s, true)",
        (str(user_id),),
    )
    connection.execute("select set_config('request.jwt.claim.role', 'authenticated', true)")


def _enqueue_operation_message(
    connection: psycopg.Connection,
    request_id: UUID,
) -> int:
    row = connection.execute(
        "select pgmq.send('game_operations', %s)",
        (Jsonb({"operation_id": str(request_id)}),),
    ).fetchone()
    assert row is not None
    message_id = int(row[0])
    connection.execute(
        "update public.game_operation_requests set queue_message_id = %s where request_id = %s",
        (message_id, request_id),
    )
    return message_id


@pytest.mark.serial
def test_rls_is_enabled_for_public_user_tables() -> None:
    """利用者dataを持つpublic tableでRLSを無効化しない。"""

    with psycopg.connect(os.environ["WEREWOLF_SUPABASE_DB_DSN"]) as connection:
        rows = connection.execute(
            """
            select relname, relrowsecurity
            from pg_class
            join pg_namespace on pg_namespace.oid = pg_class.relnamespace
            where nspname = 'public'
              and relkind = 'r'
              and relname in (
                'games',
                'game_participants',
                'game_player_observations',
                'game_operation_requests'
              )
            order by relname
            """
        ).fetchall()

    assert rows
    assert all(enabled for _, enabled in rows)


@pytest.mark.serial
def test_operation_request_has_idempotency_constraint() -> None:
    """同一利用者の同一要求をDB境界で重複登録させない。"""

    with psycopg.connect(os.environ["WEREWOLF_SUPABASE_DB_DSN"]) as connection:
        definitions = connection.execute(
            """
            select pg_get_constraintdef(oid)
            from pg_constraint
            where conrelid = 'public.game_operation_requests'::regclass
              and contype = 'u'
            """
        ).fetchall()

    assert any("owner_user_id, idempotency_key" in definition for (definition,) in definitions)


@pytest.mark.serial
def test_rls_hides_another_users_game_and_private_reveal() -> None:
    """RLSを実際に評価し、他利用者とrevealを公開しない。"""

    owner_id, other_id, game_id = uuid4(), uuid4(), uuid4()
    connection = psycopg.connect(os.environ["WEREWOLF_SUPABASE_DB_DSN"])
    try:
        _insert_user(connection, owner_id)
        _insert_user(connection, other_id)
        connection.execute(
            """
            insert into public.games (
              game_id, owner_user_id, status, phase, day, version, public_state
            ) values (%s, %s, 'running', 'night', 0, 1, '{}'::jsonb)
            """,
            (game_id, owner_id),
        )
        connection.execute(
            """
            insert into private.game_reveals (game_id, reveal_payload, state_version)
            values (%s, '{"winner":"village"}'::jsonb, 1)
            """,
            (game_id,),
        )

        _assume_authenticated_user(connection, other_id)
        with pytest.raises(InsufficientPrivilege), connection.transaction():
            connection.execute(
                "select count(*) from public.games where game_id = %s",
                (game_id,),
            )
        with pytest.raises(InsufficientPrivilege), connection.transaction():
            connection.execute(
                "select count(*) from private.game_reveals where game_id = %s",
                (game_id,),
            )
    finally:
        connection.rollback()
        connection.close()


@pytest.mark.serial
def test_operation_request_rejects_direct_authenticated_mutation() -> None:
    """queue更新をAPIへ限定し、authenticated roleの直接SQLを拒否する。"""

    owner_id, other_id = uuid4(), uuid4()
    connection = psycopg.connect(os.environ["WEREWOLF_SUPABASE_DB_DSN"])
    try:
        _insert_user(connection, owner_id)
        _insert_user(connection, other_id)
        _assume_authenticated_user(connection, owner_id)
        with pytest.raises(InsufficientPrivilege), connection.transaction():
            connection.execute(
                """
                insert into public.game_operation_requests (
                  owner_user_id, operation_type, idempotency_key
                ) values (%s, 'create_game', 'owner-request')
                """,
                (owner_id,),
            )
        with pytest.raises(InsufficientPrivilege), connection.transaction():
            connection.execute(
                """
                insert into public.game_operation_requests (
                  owner_user_id, operation_type, idempotency_key
                ) values (%s, 'create_game', 'foreign-owner')
                """,
                (other_id,),
            )
    finally:
        connection.rollback()
        connection.close()


@pytest.mark.serial
def test_worker_creates_and_advances_game_with_fake_llm() -> None:
    """workerがqueueからゲームを作成し、次の状態まで進める。"""

    dsn = os.environ["WEREWOLF_SUPABASE_DB_DSN"]
    owner_id = uuid4()
    connection = psycopg.connect(dsn)
    game_id: UUID | None = None
    try:
        _insert_user(connection, owner_id)
        settings = AppSettings(
            llm_provider="fake",
            supabase_db_dsn=dsn,
            supabase_worker_batch_size=1,
        )
        setup_catalog = build_setup_catalog(settings)
        setups = SetupApplication(setup_catalog, build_game_application_config(settings))
        create_command = setups.prepare_create(
            setup_catalog.require_document("standard_6"),
            seed=2**40,
            manual_player_id=None,
            llm_mode="fake",
            deliberation_level="standard",
        )
        create_id = connection.execute(
            """
            insert into public.game_operation_requests (
              owner_user_id, operation_type, idempotency_key, request_payload
            ) values (%s, 'create_game', 'worker-create', %s)
            returning request_id
            """,
            (
                owner_id,
                Jsonb(create_command.model_dump(mode="json")),
            ),
        ).fetchone()
        assert create_id is not None
        _enqueue_operation_message(connection, create_id[0])
        connection.commit()

        assert settings.llm_provider == "fake"
        assert process_worker_batch(settings) == 1

        created = connection.execute(
            """
            select status, result_payload
            from public.game_operation_requests
            where request_id = %s
            """,
            (create_id[0],),
        ).fetchone()
        assert created is not None
        assert created[0] == "succeeded"
        game_id = UUID(str(created[1]["game_id"]))
        initial_version = connection.execute(
            "select version from public.games where game_id = %s",
            (game_id,),
        ).fetchone()
        assert initial_version is not None

        advance_id = connection.execute(
            """
            insert into public.game_operation_requests (
              owner_user_id, operation_type, game_id, idempotency_key, expected_version
            ) values (%s, 'advance_game', %s, 'worker-advance', %s)
            returning request_id
            """,
            (owner_id, game_id, initial_version[0]),
        ).fetchone()
        assert advance_id is not None
        _enqueue_operation_message(connection, advance_id[0])
        connection.commit()
        assert process_worker_batch(settings) == 1

        advanced = connection.execute(
            """
            select status from public.game_operation_requests where request_id = %s
            """,
            (advance_id[0],),
        ).fetchone()
        current_version = connection.execute(
            "select version from public.games where game_id = %s",
            (game_id,),
        ).fetchone()
        assert advanced == ("succeeded",)
        assert current_version is not None
        assert current_version[0] > initial_version[0]
    finally:
        connection.rollback()
        if game_id is not None:
            connection.execute("delete from public.games where game_id = %s", (game_id,))
        connection.execute(
            "delete from public.game_operation_requests where owner_user_id = %s",
            (owner_id,),
        )
        connection.execute("delete from auth.users where id = %s", (owner_id,))
        connection.commit()
        connection.close()


@pytest.mark.deep
@pytest.mark.serial
def test_concurrent_workers_claim_a_request_once() -> None:
    """複数workerが同じqueue itemを同時に取得しない。"""

    dsn = os.environ["WEREWOLF_SUPABASE_DB_DSN"]
    owner_id = uuid4()
    setup = psycopg.connect(dsn)
    message_id: int | None = None
    try:
        _insert_user(setup, owner_id)
        request_row = setup.execute(
            """
            insert into public.game_operation_requests (
              owner_user_id, operation_type, idempotency_key
            ) values (%s, 'create_game', 'concurrent-claim')
            returning request_id
            """,
            (owner_id,),
        ).fetchone()
        assert request_row is not None
        request_id = request_row[0]
        message_id = _enqueue_operation_message(setup, request_id)
        setup.commit()

        def claim(worker_id: str) -> UUID | None:
            with (
                psycopg.connect(dsn, row_factory=dict_row) as connection,
                connection.transaction(),
            ):
                row = SupabaseWorkerStore(connection).claim_request(
                    worker_id=worker_id,
                    claim_seconds=30,
                )
                return row["request_id"] if row else None

        with ThreadPoolExecutor(max_workers=2) as executor:
            claimed = list(executor.map(claim, ("worker-a", "worker-b")))

        assert claimed.count(request_id) == 1
        assert claimed.count(None) == 1
    finally:
        if message_id is not None:
            setup.execute("select pgmq.archive('game_operations', %s)", (message_id,))
        setup.execute(
            "delete from public.game_operation_requests where owner_user_id = %s",
            (owner_id,),
        )
        setup.execute("delete from auth.users where id = %s", (owner_id,))
        setup.commit()
        setup.close()


@pytest.mark.deep
@pytest.mark.serial
def test_request_returns_to_queue_when_worker_stops_before_commit() -> None:
    """claim transaction中にworkerが停止しても次のworkerが要求を取得できる。"""

    dsn = os.environ["WEREWOLF_SUPABASE_DB_DSN"]
    owner_id = uuid4()
    setup = psycopg.connect(dsn)
    first = psycopg.connect(dsn, row_factory=dict_row)
    second = psycopg.connect(dsn, row_factory=dict_row)
    message_id: int | None = None
    try:
        _insert_user(setup, owner_id)
        request_row = setup.execute(
            """
            insert into public.game_operation_requests (
              owner_user_id, operation_type, idempotency_key
            ) values (%s, 'create_game', 'worker-stop')
            returning request_id
            """,
            (owner_id,),
        ).fetchone()
        assert request_row is not None
        request_id = request_row[0]
        message_id = _enqueue_operation_message(setup, request_id)
        setup.commit()
        claimed = SupabaseWorkerStore(first).claim_request(
            worker_id="stopped-worker",
            claim_seconds=30,
        )
        assert claimed is not None
        assert claimed["request_id"] == request_id
        first.rollback()

        reclaimed = SupabaseWorkerStore(second).claim_request(
            worker_id="replacement-worker",
            claim_seconds=30,
        )

        assert reclaimed is not None
        assert reclaimed["request_id"] == request_id
    finally:
        first.rollback()
        second.rollback()
        first.close()
        second.close()
        if message_id is not None:
            setup.execute("select pgmq.archive('game_operations', %s)", (message_id,))
        setup.execute(
            "delete from public.game_operation_requests where owner_user_id = %s",
            (owner_id,),
        )
        setup.execute("delete from auth.users where id = %s", (owner_id,))
        setup.commit()
        setup.close()


@pytest.mark.deep
@pytest.mark.serial
def test_game_version_update_is_serialized_by_row_lock() -> None:
    """同じgame versionの並行更新をDB row lockで直列化する。"""

    dsn = os.environ["WEREWOLF_SUPABASE_DB_DSN"]
    owner_id, game_id = uuid4(), uuid4()
    setup = psycopg.connect(dsn)
    first = psycopg.connect(dsn)
    second = psycopg.connect(dsn)
    try:
        _insert_user(setup, owner_id)
        setup.execute(
            """
            insert into public.games (
              game_id, owner_user_id, status, phase, day, version, public_state
            ) values (%s, %s, 'running', 'night', 0, 1, '{}'::jsonb)
            """,
            (game_id, owner_id),
        )
        setup.commit()

        locked = first.execute(
            "select version from public.games where game_id = %s for update",
            (game_id,),
        ).fetchone()
        assert locked == (1,)
        second.execute("set local lock_timeout = '250ms'")
        with pytest.raises(LockNotAvailable):
            second.execute(
                "select version from public.games where game_id = %s for update",
                (game_id,),
            )
        second.rollback()
        first.rollback()

        available = second.execute(
            "select version from public.games where game_id = %s for update",
            (game_id,),
        ).fetchone()
        assert available == (1,)
    finally:
        first.rollback()
        second.rollback()
        first.close()
        second.close()
        setup.execute("delete from public.games where game_id = %s", (game_id,))
        setup.execute("delete from auth.users where id = %s", (owner_id,))
        setup.commit()
        setup.close()


pytestmark = [pytest.mark.supabase]
