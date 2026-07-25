"""Supabase persistence operations used by the asynchronous worker."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from werewolf_agent.adapters.supabase.json import jsonb
from werewolf_agent.application.replay import checksum_payload
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import ProblemDetails


@dataclass(frozen=True, slots=True)
class PlayerParticipant:
    """One authenticated user bound to a player seat."""

    user_id: str
    player_id: str


class SupabaseWorkerStore:
    """Keep worker queue and materialized-view SQL inside the Supabase adapter."""

    def __init__(self, connection: Any) -> None:
        """Bind operations to one worker database connection."""
        self._connection = connection

    def claim_request(self, *, worker_id: str, claim_seconds: int) -> dict[str, Any] | None:
        """Claim the oldest available operation request."""
        row = self._connection.execute(
            """
            with next_request as (
              select request_id
              from public.game_operation_requests
              where status = 'queued'
                 or (status = 'running' and claimed_until < timezone('utc', now()))
              order by created_at
              for update skip locked
              limit 1
            )
            update public.game_operation_requests r
            set status = 'running',
                worker_id = %s,
                attempt_count = attempt_count + 1,
                started_at = coalesce(started_at, timezone('utc', now())),
                claimed_until = timezone('utc', now()) + make_interval(secs => %s)
            where r.request_id = (select request_id from next_request)
            returning *
            """,
            (worker_id, claim_seconds),
        ).fetchone()
        return dict(row) if row is not None else None

    def verify_creation_llm_mode(
        self,
        *,
        owner_user_id: str,
        requested_mode: str,
    ) -> Literal["fake", "paid"]:
        """Revalidate the accepted LLM mode against the current membership."""
        if requested_mode not in {"fake", "paid"}:
            raise AppError(
                "The stored LLM mode is invalid.",
                code=ErrorCode.INTERNAL_UNEXPECTED,
            )
        row = self._connection.execute(
            """
            select is_anonymous from auth.users where id = %s limit 1
            """,
            (owner_user_id,),
        ).fetchone()
        if row is None:
            raise AppError(
                "利用者を確認できませんでした。",
                code=ErrorCode.AUTHENTICATION_REQUIRED,
            )
        if requested_mode == "paid" and bool(row["is_anonymous"]):
            raise AppError(
                "有料LLMは登録済み利用者だけが使用できます。",
                code=ErrorCode.AUTHORIZATION_FAILED,
            )
        return cast(Literal["fake", "paid"], requested_mode)

    def game_llm_mode(self, game_id: str) -> str:
        """Return the persisted LLM mode for a game."""
        row = self._connection.execute(
            """select llm_mode from public.games where game_id = %s limit 1""",
            (game_id,),
        ).fetchone()
        if row is None:
            raise AppError("ゲームが見つかりません。", code=ErrorCode.RESOURCE_NOT_FOUND)
        return str(row["llm_mode"])

    def add_participant(
        self,
        *,
        game_id: str,
        user_id: str,
        player_id: str,
        role: str,
    ) -> None:
        """Persist an owner, player, or observer relationship."""
        self._connection.execute(
            """
            insert into public.game_participants (game_id, user_id, player_id, participant_role)
            values (%s, %s, %s, %s)
            on conflict (game_id, user_id, player_id) do nothing
            """,
            (game_id, user_id, player_id, role),
        )

    def owns_player(self, *, game_id: str, player_id: str, user_id: str) -> bool:
        """Return whether a user currently owns a playable seat."""
        row = self._connection.execute(
            """
            select 1 from public.game_participants
            where game_id = %s and player_id = %s and user_id = %s
              and participant_role in ('owner', 'player')
            limit 1
            """,
            (game_id, player_id, user_id),
        ).fetchone()
        return row is not None

    def participates(self, *, game_id: str, user_id: str) -> bool:
        """Return whether a user currently participates in a game."""
        row = self._connection.execute(
            """
            select 1 from public.game_participants
            where game_id = %s and user_id = %s
              and participant_role in ('owner', 'player', 'observer')
            limit 1
            """,
            (game_id, user_id),
        ).fetchone()
        return row is not None

    def player_participants(self, game_id: str) -> tuple[PlayerParticipant, ...]:
        """Return authenticated player seats that need private observations."""
        rows = self._connection.execute(
            """
            select user_id, player_id from public.game_participants
            where game_id = %s and participant_role in ('owner', 'player')
            """,
            (game_id,),
        ).fetchall()
        return tuple(
            PlayerParticipant(user_id=str(row["user_id"]), player_id=str(row["player_id"]))
            for row in rows
            if str(row["player_id"]) != "observer"
        )

    def save_observation(
        self,
        *,
        game_id: str,
        participant: PlayerParticipant,
        state_version: int,
        observation: Mapping[str, Any],
    ) -> None:
        """Upsert one private player observation."""
        self._connection.execute(
            """
            insert into private.game_player_observations (
              game_id, player_id, user_id, state_version, observation, updated_at
            ) values (%s, %s, %s, %s, %s, timezone('utc', now()))
            on conflict (game_id, player_id, user_id) do update set
              state_version = excluded.state_version,
              observation = excluded.observation,
              updated_at = excluded.updated_at
            """,
            (
                game_id,
                participant.player_id,
                participant.user_id,
                state_version,
                jsonb(dict(observation)),
            ),
        )

    def delete_reveal(self, game_id: str) -> None:
        """Remove a materialized reveal when the feature is disabled."""
        self._connection.execute(
            """delete from private.game_reveals where game_id = %s""",
            (game_id,),
        )

    def save_reveal(self, *, game_id: str, payload: Mapping[str, Any], version: int) -> None:
        """Upsert the administrator-only reveal payload."""
        self._connection.execute(
            """
            insert into private.game_reveals (game_id, reveal_payload, state_version, updated_at)
            values (%s, %s, %s, timezone('utc', now()))
            on conflict (game_id) do update set
              reveal_payload = excluded.reveal_payload,
              state_version = excluded.state_version,
              updated_at = excluded.updated_at
            """,
            (game_id, jsonb(dict(payload)), version),
        )

    def complete_request(
        self,
        request: Mapping[str, Any],
        result_payload: Mapping[str, Any],
    ) -> None:
        """Complete a request only while the current worker still owns its claim."""
        result = self._connection.execute(
            """
            update public.game_operation_requests
            set status = 'succeeded', result_payload = %s,
                completed_at = timezone('utc', now()), claimed_until = null
            where request_id = %s and status = 'running'
              and attempt_count = %s and worker_id = %s
            """,
            (
                jsonb(dict(result_payload)),
                request["request_id"],
                request["attempt_count"],
                request["worker_id"],
            ),
        )
        if getattr(result, "rowcount", 1) != 1:
            raise AppError(
                "操作の処理権限が更新されました。",
                code=ErrorCode.API_UNAVAILABLE,
                retryable=True,
            )

    def record_accepted_command(
        self,
        request: Mapping[str, Any],
        result_payload: Mapping[str, Any],
    ) -> None:
        """Persist the accepted command and its audit event."""
        state = _object(result_payload.get("state"))
        version = int(state.get("version") or 1)
        game_id = str(result_payload.get("game_id") or request.get("game_id") or "")
        payload = {
            "operation_type": str(request["operation_type"]),
            "expected_version": request.get("expected_version"),
            "player_id": request.get("player_id"),
            "request": _object(request.get("request_payload")),
        }
        self._connection.execute(
            """
            insert into private.accepted_commands (
              game_id, operation_id, version, command_type, actor_user_id, payload, checksum
            ) values (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                game_id,
                request["request_id"],
                version,
                request["operation_type"],
                request["owner_user_id"],
                jsonb(payload),
                checksum_payload(payload),
            ),
        )
        self._record_audit(
            request,
            action="operation.succeeded",
            metadata={"game_id": game_id, "version": version},
        )

    def fail_request(self, request: Mapping[str, Any], problem: ProblemDetails) -> None:
        """Persist a safe failure only while the worker still owns its claim."""
        result = self._connection.execute(
            """
            update public.game_operation_requests
            set status = 'failed', error_payload = %s,
                completed_at = timezone('utc', now()), claimed_until = null
            where request_id = %s and status = 'running'
              and attempt_count = %s and worker_id = %s
            """,
            (
                jsonb(problem.model_dump(mode="json")),
                request["request_id"],
                request["attempt_count"],
                request["worker_id"],
            ),
        )
        if getattr(result, "rowcount", 1) == 1:
            self._record_audit(
                request,
                action="operation.failed",
                metadata={"error_code": problem.code},
            )

    def _record_audit(
        self,
        request: Mapping[str, Any],
        *,
        action: str,
        metadata: Mapping[str, Any],
    ) -> None:
        self._connection.execute(
            """
            insert into private.audit_events (
              actor_user_id, action, target_type, target_id, metadata
            ) values (%s, %s, 'operation', %s, %s)
            """,
            (
                request["owner_user_id"],
                action,
                request["request_id"],
                jsonb(dict(metadata)),
            ),
        )


def _object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


__all__ = ["PlayerParticipant", "SupabaseWorkerStore"]
