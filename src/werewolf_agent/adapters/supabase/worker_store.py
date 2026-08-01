"""Supabase persistence operations used by the asynchronous worker."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from werewolf_agent.adapters.supabase.json import jsonb
from werewolf_agent.application.versions import REPLAY_FORMAT_VERSION
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import ProblemDetails
from werewolf_agent.setup import checksum_payload


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

    def claim_request(
        self,
        *,
        worker_id: str,
        claim_seconds: int,
        poll_seconds: int = 0,
    ) -> dict[str, Any] | None:
        """Read one PGMQ message and bind its ledger row to this worker."""
        requests = self.claim_requests(
            worker_id=worker_id,
            claim_seconds=claim_seconds,
            quantity=1,
            poll_seconds=poll_seconds,
        )
        return requests[0] if requests else None

    def claim_requests(
        self,
        *,
        worker_id: str,
        claim_seconds: int,
        quantity: int,
        poll_seconds: int = 5,
    ) -> list[dict[str, Any]]:
        """Read a bounded PGMQ batch and bind each ledger row to this worker."""
        if poll_seconds > 0:
            messages = self._connection.execute(
                """
                select * from pgmq.read_with_poll(
                  'game_operations', %s, %s, %s, 100
                )
                """,
                (claim_seconds, quantity, poll_seconds),
            ).fetchall()
        else:
            messages = self._connection.execute(
                """
                select * from pgmq.read('game_operations', %s, %s)
                """,
                (claim_seconds, quantity),
            ).fetchall()
        requests: list[dict[str, Any]] = []
        for message in messages:
            payload = message.get("message")
            operation_id = (
                str(payload.get("operation_id") or "") if isinstance(payload, Mapping) else ""
            )
            row = self._connection.execute(
                """
                update public.game_operation_requests
                set status = 'running', worker_id = %s, attempt_count = %s,
                    started_at = coalesce(started_at, timezone('utc', now()))
                where request_id = %s and queue_message_id = %s
                  and status in ('queued', 'running')
                returning *
                """,
                (worker_id, int(message["read_ct"]), operation_id, int(message["msg_id"])),
            ).fetchone()
            if row is None:
                self.archive_message(int(message["msg_id"]))
                continue
            result = dict(row)
            result["queue_message_id"] = int(message["msg_id"])
            requests.append(result)
        return requests

    def renew_claim(
        self,
        request: Mapping[str, Any],
        *,
        claim_seconds: int,
    ) -> bool:
        """Extend visibility only while this worker still owns the ledger claim."""
        row = self._connection.execute(
            """
            select pgmq.set_vt('game_operations', %s, %s) as renewed
            where exists (
              select 1 from public.game_operation_requests
              where request_id = %s and status = 'running'
                and attempt_count = %s and worker_id = %s
                and queue_message_id = %s
            )
            """,
            (
                int(request["queue_message_id"]),
                claim_seconds,
                request["request_id"],
                request["attempt_count"],
                request["worker_id"],
                int(request["queue_message_id"]),
            ),
        ).fetchone()
        return row is not None

    def archive_message(self, message_id: int) -> None:
        """Archive one consumed PGMQ message."""
        self._connection.execute(
            "select pgmq.archive('game_operations', %s)",
            (message_id,),
        )

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
                completed_at = timezone('utc', now())
            where request_id = %s and status = 'running'
              and attempt_count = %s and worker_id = %s and queue_message_id = %s
            """,
            (
                jsonb(dict(result_payload)),
                request["request_id"],
                request["attempt_count"],
                request["worker_id"],
                request["queue_message_id"],
            ),
        )
        if getattr(result, "rowcount", 1) != 1:
            raise AppError(
                "操作の処理権限が更新されました。",
                code=ErrorCode.API_UNAVAILABLE,
                retryable=True,
            )
        self.archive_message(int(request["queue_message_id"]))

    def record_accepted_command(
        self,
        request: Mapping[str, Any],
        result_payload: Mapping[str, Any],
    ) -> None:
        """Persist the accepted command and its audit event."""
        state = _object(result_payload.get("state"))
        version = int(state.get("version") or 1)
        game_id = str(result_payload.get("game_id") or request.get("game_id") or "")
        normalized_request = _object(request.get("request_payload"))
        payload: dict[str, Any] = {
            "operation_type": str(request["operation_type"]),
            "actor_user_id": str(request["owner_user_id"]),
            "expected_version": request.get("expected_version"),
            "player_id": request.get("player_id"),
            "request": normalized_request,
        }
        decisions = self._connection.execute(
            """
            select parsed_decision
            from private.llm_traces
            where operation_id = %s and parsed_decision is not null
            order by created_at, invocation_id
            """,
            (request["request_id"],),
        ).fetchall()
        payload["domain_actions"] = [_object(row["parsed_decision"]) for row in decisions]
        if request["operation_type"] == "create_game":
            snapshot_row = self._connection.execute(
                """
                select seed, config, private_state
                from private.game_snapshots
                where game_id = %s
                """,
                (game_id,),
            ).fetchone()
            if snapshot_row is None:
                raise RuntimeError("Created game snapshot is missing.")
            private_state = _object(snapshot_row["private_state"])
            players = _object(private_state.get("players"))
            effective_seed = snapshot_row["seed"]
            normalized_request["seed"] = effective_seed
            stored_config = _object(snapshot_row["config"])
            payload["replay"] = {
                "format_version": REPLAY_FORMAT_VERSION,
                "seed": effective_seed,
                "setup_document": _object(stored_config.get("setup_document")),
                "setup_checksum": stored_config.get("setup_checksum"),
                "mechanics_checksum": stored_config.get("mechanics_checksum"),
                "roster_checksum": stored_config.get("roster_checksum"),
                "rule_pack_manifest": _object(stored_config.get("rule_pack_manifest")),
                "players": [
                    {"id": str(player["id"]), "name": str(player["name"])}
                    for player in map(_object, players.values())
                ],
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
                completed_at = timezone('utc', now())
            where request_id = %s and status = 'running'
              and attempt_count = %s and worker_id = %s and queue_message_id = %s
            """,
            (
                jsonb(problem.model_dump(mode="json")),
                request["request_id"],
                request["attempt_count"],
                request["worker_id"],
                request["queue_message_id"],
            ),
        )
        if getattr(result, "rowcount", 1) == 1:
            self._record_audit(
                request,
                action="operation.failed",
                metadata={"error_code": problem.code},
            )
            self.archive_message(int(request["queue_message_id"]))

    def retry_request(self, request: Mapping[str, Any], problem: ProblemDetails) -> None:
        """Return a retryable failure to the queue without archiving its message."""
        result = self._connection.execute(
            """
            update public.game_operation_requests
            set status = 'queued', worker_id = null, error_payload = %s
            where request_id = %s and status = 'running'
              and attempt_count = %s and worker_id = %s and queue_message_id = %s
            """,
            (
                jsonb(problem.model_dump(mode="json")),
                request["request_id"],
                request["attempt_count"],
                request["worker_id"],
                request["queue_message_id"],
            ),
        )
        if getattr(result, "rowcount", 1) == 1:
            self._connection.execute(
                "select * from pgmq.set_vt('game_operations', %s, 1)",
                (int(request["queue_message_id"]),),
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
