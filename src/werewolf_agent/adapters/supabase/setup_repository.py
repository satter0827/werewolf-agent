"""Supabase persistence for immutable user setup revisions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from werewolf_agent.application.errors import AppError, ErrorCode
from werewolf_agent.application.ports import SetupRepository
from werewolf_agent.application.setup_records import SavedSetupRevision, SavedSetupSummary
from werewolf_agent.setup import GameSetupDocument


class SupabaseSetupRepository(SetupRepository):
    """Direct-Postgres repository with explicit owner filtering on every query."""

    def __init__(self, connection: Any) -> None:
        """Bind one transaction-scoped Postgres connection."""
        self._connection = connection

    def create(
        self,
        *,
        owner_user_id: str,
        display_name: str,
        document: GameSetupDocument,
        setup_checksum: str,
        mechanics_checksum: str,
        max_setups: int,
    ) -> SavedSetupRevision:
        """Create an owned setup and its first immutable revision."""
        owner_id = UUID(owner_user_id)
        self._connection.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (str(owner_id),),
        )
        count_row = self._connection.execute(
            "select count(*) as setup_count from private.user_setups where owner_user_id = %s",
            (owner_id,),
        ).fetchone()
        if count_row is None or int(count_row["setup_count"]) >= max_setups:
            raise AppError(
                "保存できるゲーム設定数が上限に達しました。",
                code=ErrorCode.SETUP_LIMIT_REACHED,
            )
        setup_id = uuid4()
        self._connection.execute(
            """
            insert into private.user_setups (setup_id, owner_user_id, display_name)
            values (%s, %s, %s)
            """,
            (setup_id, owner_id, display_name),
        )
        self._insert_revision(
            setup_id,
            revision=1,
            document=document,
            setup_checksum=setup_checksum,
            mechanics_checksum=mechanics_checksum,
        )
        result = self.get(str(setup_id), owner_user_id=owner_user_id, revision=1)
        if result is None:
            raise RuntimeError("created setup revision could not be loaded")
        return result

    def list_setups(
        self, *, owner_user_id: str, limit: int, offset: int
    ) -> list[SavedSetupSummary]:
        """Return setup summaries filtered by owner."""
        rows = self._connection.execute(
            """
            select s.setup_id, s.display_name, s.created_at,
                   r.revision as latest_revision, r.created_at as updated_at
            from private.user_setups s
            join lateral (
              select revision, created_at
              from private.user_setup_revisions
              where setup_id = s.setup_id
              order by revision desc
              limit 1
            ) r on true
            where s.owner_user_id = %s
            order by r.created_at desc, s.setup_id
            limit %s offset %s
            """,
            (UUID(owner_user_id), limit, offset),
        ).fetchall()
        summaries: list[SavedSetupSummary] = []
        for row in rows:
            payload = dict(row)
            payload["setup_id"] = str(payload["setup_id"])
            summaries.append(SavedSetupSummary.model_validate(payload))
        return summaries

    def get(
        self,
        setup_id: str,
        *,
        owner_user_id: str,
        revision: int | None = None,
    ) -> SavedSetupRevision | None:
        """Return one owned revision or the latest owned revision."""
        try:
            parsed_id = UUID(setup_id)
        except ValueError:
            return None
        row = self._connection.execute(
            """
            select s.setup_id, s.display_name, r.revision, r.document,
                   r.setup_checksum, r.mechanics_checksum, r.created_at
            from private.user_setups s
            join private.user_setup_revisions r on r.setup_id = s.setup_id
            where s.setup_id = %s and s.owner_user_id = %s
              and (%s::integer is null or r.revision = %s::integer)
            order by r.revision desc
            limit 1
            """,
            (parsed_id, UUID(owner_user_id), revision, revision),
        ).fetchone()
        return None if row is None else _revision(row)

    def list_revisions(
        self,
        setup_id: str,
        *,
        owner_user_id: str,
        limit: int,
        offset: int,
    ) -> list[SavedSetupRevision]:
        """Return immutable revisions filtered by setup owner."""
        try:
            parsed_id = UUID(setup_id)
        except ValueError:
            return []
        rows = self._connection.execute(
            """
            select s.setup_id, s.display_name, r.revision, r.document,
                   r.setup_checksum, r.mechanics_checksum, r.created_at
            from private.user_setups s
            join private.user_setup_revisions r on r.setup_id = s.setup_id
            where s.setup_id = %s and s.owner_user_id = %s
            order by r.revision desc
            limit %s offset %s
            """,
            (parsed_id, UUID(owner_user_id), limit, offset),
        ).fetchall()
        return [_revision(row) for row in rows]

    def add_revision(
        self,
        setup_id: str,
        *,
        owner_user_id: str,
        expected_revision: int,
        document: GameSetupDocument,
        setup_checksum: str,
        mechanics_checksum: str,
        max_revisions: int,
    ) -> SavedSetupRevision:
        """Lock an owned setup and append the expected next revision."""
        try:
            parsed_id = UUID(setup_id)
        except ValueError as exc:
            raise AppError(
                "指定したゲーム設定が見つかりません。",
                code=ErrorCode.RESOURCE_NOT_FOUND,
            ) from exc
        parent = self._connection.execute(
            """
            select setup_id
            from private.user_setups
            where setup_id = %s and owner_user_id = %s
            for update
            """,
            (parsed_id, UUID(owner_user_id)),
        ).fetchone()
        if parent is None:
            raise AppError(
                "指定したゲーム設定が見つかりません。",
                code=ErrorCode.RESOURCE_NOT_FOUND,
            )
        row = self._connection.execute(
            """
            select max(revision) as latest_revision
            from private.user_setup_revisions
            where setup_id = %s
            """,
            (parsed_id,),
        ).fetchone()
        latest_revision = int(row["latest_revision"])
        if latest_revision != expected_revision:
            raise AppError(
                "別の版が先に保存されています。最新の設定を読み直してください。",
                code=ErrorCode.SETUP_REVISION_CONFLICT,
                context={
                    "expected_revision": expected_revision,
                    "latest_revision": latest_revision,
                },
            )
        if latest_revision >= max_revisions:
            raise AppError(
                "保存できるゲーム設定の版数が上限に達しました。",
                code=ErrorCode.SETUP_REVISION_LIMIT_REACHED,
            )
        next_revision = latest_revision + 1
        self._insert_revision(
            parsed_id,
            revision=next_revision,
            document=document,
            setup_checksum=setup_checksum,
            mechanics_checksum=mechanics_checksum,
        )
        result = self.get(setup_id, owner_user_id=owner_user_id, revision=next_revision)
        if result is None:
            raise RuntimeError("saved setup revision could not be loaded")
        return result

    def _insert_revision(
        self,
        setup_id: UUID,
        *,
        revision: int,
        document: GameSetupDocument,
        setup_checksum: str,
        mechanics_checksum: str,
    ) -> None:
        self._connection.execute(
            """
            insert into private.user_setup_revisions (
              setup_id, revision, schema_version, document,
              setup_checksum, mechanics_checksum
            ) values (%s, %s, %s, %s, %s, %s)
            """,
            (
                setup_id,
                revision,
                document.schema_version,
                Jsonb(document.to_mapping()),
                setup_checksum,
                mechanics_checksum,
            ),
        )


def _revision(row: Mapping[str, Any]) -> SavedSetupRevision:
    payload = dict(row)
    payload["setup_id"] = str(payload["setup_id"])
    payload["document"] = GameSetupDocument.from_mapping(payload["document"])
    return SavedSetupRevision.model_validate(payload)


__all__ = ["SupabaseSetupRepository"]
