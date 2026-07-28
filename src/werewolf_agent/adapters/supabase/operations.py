"""Supabase operation queue and access-control adapters."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from psycopg.types.json import Jsonb

from werewolf_agent.application.operations import QueuedOperation
from werewolf_agent.application.replay import checksum_payload
from werewolf_agent.contracts import AppError, ErrorCode, ResourceNotFoundError


class SupabaseOperationQueue:
    """Persist idempotent commands in the Supabase operation queue."""

    def __init__(self, connection: Any) -> None:
        """Bind the adapter to one request transaction."""
        self._connection = connection

    def enqueue(
        self,
        *,
        operation_type: str,
        owner_user_id: str,
        idempotency_key: str,
        request_payload: dict[str, Any],
        llm_mode: str | None,
        game_id: str | None = None,
        player_id: str | None = None,
        expected_version: int | None = None,
    ) -> QueuedOperation:
        """Insert or return a command with the same caller idempotency key."""
        effective_llm_mode = self._resolve_llm_mode(game_id=game_id, llm_mode=llm_mode)
        request_hash = checksum_payload(
            {
                "operation_type": operation_type,
                "game_id": game_id,
                "player_id": player_id,
                "expected_version": expected_version,
                "llm_mode": effective_llm_mode,
                "request_payload": request_payload,
            }
        )
        row = self._connection.execute(
            """
            insert into public.game_operation_requests (
              operation_type, owner_user_id, idempotency_key, request_payload,
              game_id, player_id, expected_version, llm_mode, request_hash
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (owner_user_id, idempotency_key) do nothing
            returning *
            """,
            (
                operation_type,
                owner_user_id,
                idempotency_key,
                Jsonb(request_payload),
                game_id,
                player_id,
                expected_version,
                effective_llm_mode,
                request_hash,
            ),
        ).fetchone()
        inserted = row is not None
        if row is None:
            row = self._connection.execute(
                """
                select * from public.game_operation_requests
                where owner_user_id = %s and idempotency_key = %s
                limit 1
                """,
                (owner_user_id, idempotency_key),
            ).fetchone()
        if row is None:
            raise AppError("操作を受け付けられませんでした。", code=ErrorCode.API_UNAVAILABLE)
        if row.get("request_hash") != request_hash:
            raise AppError(
                "このIdempotency-Keyは別の操作で使用済みです。",
                code=ErrorCode.REQUEST_IDEMPOTENCY_CONFLICT,
            )
        if inserted:
            message_row = self._connection.execute(
                "select pgmq.send('game_operations', %s) as msg_id",
                (Jsonb({"operation_id": str(row["request_id"])}),),
            ).fetchone()
            if message_row is None:
                raise AppError(
                    "操作をqueueへ登録できませんでした。", code=ErrorCode.API_UNAVAILABLE
                )
            message_id = int(message_row["msg_id"])
            row = self._connection.execute(
                """
                update public.game_operation_requests
                set queue_message_id = %s
                where request_id = %s
                returning *
                """,
                (message_id, row["request_id"]),
            ).fetchone()
            if row is None:
                raise AppError(
                    "操作をqueueへ登録できませんでした。", code=ErrorCode.API_UNAVAILABLE
                )
        return _operation_from_row(row)

    def _resolve_llm_mode(self, *, game_id: str | None, llm_mode: str | None) -> str:
        if game_id is None:
            if llm_mode is None:
                raise AppError(
                    "ゲーム作成時のLLMモードがありません。",
                    code=ErrorCode.INTERNAL_UNEXPECTED,
                )
            return llm_mode
        row = self._connection.execute(
            """
            select llm_mode
            from public.games
            where game_id = %s
            limit 1
            """,
            (game_id,),
        ).fetchone()
        if row is None:
            raise ResourceNotFoundError("ゲームが見つかりません。")
        return str(row["llm_mode"])

    def get(self, operation_id: str, *, owner_user_id: str) -> QueuedOperation | None:
        """Return one operation only when it belongs to the caller."""
        row = self._connection.execute(
            """
            select *
            from public.game_operation_requests
            where request_id = %s and owner_user_id = %s
            limit 1
            """,
            (operation_id, owner_user_id),
        ).fetchone()
        return _operation_from_row(row) if row is not None else None


class SupabaseAccessPolicy:
    """Authorize requests from participant records written by the worker."""

    def __init__(self, connection: Any) -> None:
        """Bind the policy to one request transaction."""
        self._connection = connection

    def require_game_access(self, game_id: str, *, user_id: str) -> None:
        """Require any participant relationship with the game."""
        row = self._connection.execute(
            """
            select 1 from public.game_participants
            where game_id = %s and user_id = %s
            limit 1
            """,
            (game_id, user_id),
        ).fetchone()
        if row is None:
            _forbidden()

    def require_player_access(self, game_id: str, player_id: str, *, user_id: str) -> None:
        """Require ownership of one manual player seat."""
        row = self._connection.execute(
            """
            select 1 from public.game_participants
            where game_id = %s and player_id = %s and user_id = %s
              and participant_role in ('owner', 'player')
            limit 1
            """,
            (game_id, player_id, user_id),
        ).fetchone()
        if row is None:
            _forbidden()


def _operation_from_row(row: Mapping[str, Any]) -> QueuedOperation:
    raw_status = str(row.get("status") or "queued")
    status = {
        "queued": "queued",
        "running": "running",
        "completed": "succeeded",
        "succeeded": "succeeded",
        "failed": "failed",
        "cancelled": "failed",
    }.get(raw_status, "failed")
    return QueuedOperation(
        operation_id=str(row["request_id"]),
        operation_type=str(row["operation_type"]),
        status=status,  # type: ignore[arg-type]
        owner_user_id=str(row["owner_user_id"]),
        game_id=str(row["game_id"]) if row.get("game_id") else None,
        expected_version=(
            int(row["expected_version"]) if row.get("expected_version") is not None else None
        ),
        result=_object_or_none(row.get("result_payload")),
        error=_object_or_none(row.get("error_payload")),
        created_at=_datetime(row.get("created_at")),
        updated_at=_datetime(row.get("updated_at")),
    )


def _object_or_none(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, Mapping) else None


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime.now(UTC)


def _forbidden() -> None:
    raise AppError(
        "このゲームを操作する権限がありません。",
        code=ErrorCode.AUTHORIZATION_FAILED,
    )


__all__ = ["SupabaseAccessPolicy", "SupabaseOperationQueue"]
