"""Administrator-only Supabase diagnostic queries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class SupabaseAdminDiagnostics:
    """Read bounded diagnostic records from non-public persistence."""

    def __init__(self, connection: Any) -> None:
        """Bind diagnostic reads to one request transaction."""
        self._connection = connection

    def operation(self, operation_id: str) -> Mapping[str, Any] | None:
        """Return one operation without its request payload or owner identity."""
        row = self._connection.execute(
            """
            select request_id as operation_id, operation_type, status, game_id,
                   attempt_count, worker_id, created_at, started_at, completed_at,
                   error_payload
            from public.game_operation_requests
            where request_id = %s
            limit 1
            """,
            (operation_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def traces(self, game_id: str, *, limit: int) -> list[Mapping[str, Any]]:
        """Return bounded private trace metadata without prompts or raw responses."""
        return list(
            self._connection.execute(
                """
                select invocation_id, game_id, operation_id, state_version,
                       provider, model, player_id, phase, day, prompt_hash,
                       latency_ms, created_at
                from private.llm_traces
                where game_id = %s
                order by created_at desc
                limit %s
                """,
                (game_id, limit),
            ).fetchall()
        )

    def usage(self, game_id: str) -> Mapping[str, Any]:
        """Return aggregate LLM usage for one game."""
        row = self._connection.execute(
            """
            select %s::uuid as game_id,
                   count(*)::integer as invocation_count,
                   coalesce(sum(input_tokens), 0)::bigint as input_tokens,
                   coalesce(sum(output_tokens), 0)::bigint as output_tokens,
                   coalesce(sum(cost_micros), 0)::bigint as cost_micros
            from private.llm_usage
            where game_id = %s
            """,
            (game_id, game_id),
        ).fetchone()
        return dict(row or {})


__all__ = ["SupabaseAdminDiagnostics"]
