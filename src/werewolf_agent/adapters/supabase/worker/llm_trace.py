"""Supabase-backed LLM trace sink."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from werewolf_agent.agents.tracing import LlmInvocationTrace


class SupabaseLlmTraceSink:
    """Persist LLM invocation traces into the admin-only trace table."""

    def __init__(
        self,
        connection: Any,
        *,
        game_id: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
        state_version: int | None = None,
    ) -> None:
        """Create a sink bound to one worker transaction."""
        self._connection = connection
        self._game_id = game_id
        self._request_id = request_id
        self._trace_id = trace_id
        self._state_version = state_version

    def record_invocation(self, trace: LlmInvocationTrace) -> None:
        """Persist one LLM invocation trace."""
        self._connection.execute(
            """
            insert into public.llm_invocations (
              game_id, request_id, trace_id, provider, model, player_id,
              phase, day, state_version, prompt_messages, prompt_hash,
              request_payload, raw_response, parsed_decision, error_payload, latency_ms
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                self._game_id,
                self._request_id,
                self._trace_id,
                trace.provider,
                trace.model,
                trace.player_id,
                trace.phase,
                trace.day,
                self._state_version,
                Jsonb(list(trace.prompt_messages)),
                trace.prompt_hash,
                Jsonb(dict(trace.request_payload)),
                Jsonb(dict(trace.raw_response or {})) if trace.raw_response is not None else None,
                Jsonb(dict(trace.parsed_decision or {}))
                if trace.parsed_decision is not None
                else None,
                Jsonb(dict(trace.error_payload or {})) if trace.error_payload is not None else None,
                trace.latency_ms,
            ),
        )
