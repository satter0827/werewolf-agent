"""Private Supabase-backed LLM trace sink."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb

from werewolf_agent.agents.tracing import LlmInvocationTrace
from werewolf_agent.application.replay import checksum_payload


class BufferedLlmTraceSink:
    """Collect traces while the worker is outside a database transaction."""

    def __init__(self) -> None:
        """Create an empty in-memory trace buffer."""
        self.records: list[LlmInvocationTrace] = []

    def record_invocation(self, trace: LlmInvocationTrace) -> None:
        """Append one immutable trace to the in-memory buffer."""
        self.records.append(trace)

    def flush_to(self, sink: SupabaseLlmTraceSink) -> None:
        """Persist every buffered trace through a transaction-bound sink."""
        for trace in self.records:
            sink.record_invocation(trace)


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
            insert into private.llm_traces (
              game_id, operation_id, trace_id, provider, model, player_id,
              phase, day, state_version, prompt_messages, prompt_hash,
              prompt_version, setup_checksum, mechanics_checksum, observation_checksum,
              request_payload, raw_response, parsed_decision, error_payload, latency_ms
            )
            values (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
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
                trace.prompt_version,
                trace.setup_checksum,
                trace.mechanics_checksum,
                trace.observation_checksum,
                Jsonb(dict(trace.request_payload)),
                Jsonb(dict(trace.raw_response or {})) if trace.raw_response is not None else None,
                Jsonb(dict(trace.parsed_decision or {}))
                if trace.parsed_decision is not None
                else None,
                Jsonb(dict(trace.error_payload or {})) if trace.error_payload is not None else None,
                trace.latency_ms,
            ),
        )
        input_tokens, output_tokens = _token_usage(trace.raw_response)
        self._connection.execute(
            """
            insert into private.llm_usage (
              actor_user_id, game_id, operation_id, provider, model,
              input_tokens, output_tokens, cost_micros
            )
            values (
              (select owner_user_id from public.game_operation_requests where request_id = %s),
              %s, %s, %s, %s, %s, %s, 0
            )
            """,
            (
                self._request_id,
                self._game_id,
                self._request_id,
                trace.provider,
                trace.model,
                input_tokens,
                output_tokens,
            ),
        )
        if trace.parsed_decision is not None and self._game_id is not None:
            decision = dict(trace.parsed_decision)
            self._connection.execute(
                """
                insert into private.agent_decisions (
                  game_id, operation_id, state_version, player_id, decision, checksum
                )
                values (%s, %s, %s, %s, %s, %s)
                """,
                (
                    self._game_id,
                    self._request_id,
                    self._state_version or 1,
                    trace.player_id,
                    Jsonb(decision),
                    checksum_payload(decision),
                ),
            )


def _token_usage(raw_response: Any) -> tuple[int, int]:
    if not isinstance(raw_response, Mapping):
        return 0, 0
    usage = raw_response.get("usage_metadata") or raw_response.get("usage")
    if not isinstance(usage, Mapping):
        return 0, 0
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
    return _non_negative_int(input_tokens), _non_negative_int(output_tokens)


def _non_negative_int(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0
