"""Tests for durable LLM trace accounting semantics."""

from __future__ import annotations

from typing import Any

from werewolf_agent.adapters.llm.tracing import LlmInvocationTrace
from werewolf_agent.adapters.supabase.llm_trace import SupabaseLlmTraceSink


class RecordingConnection:
    """Record SQL statements without requiring PostgreSQL."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def execute(self, statement: str, parameters: object) -> None:
        self.calls.append((statement, parameters))


def _trace(**updates: Any) -> LlmInvocationTrace:
    values: dict[str, Any] = {
        "provider": "fake",
        "model": "fake-list-chat-model",
        "player_id": "p1",
        "phase": "voting",
        "day": 1,
        "prompt_messages": [],
        "prompt_hash": "checksum",
    }
    values.update(updates)
    return LlmInvocationTrace(**values)


def test_usage_row_is_not_written_when_provider_does_not_report_tokens() -> None:
    connection = RecordingConnection()
    sink = SupabaseLlmTraceSink(connection, game_id="game-1", request_id="request-1")

    sink.record_invocation(_trace())

    assert len(connection.calls) == 1
    assert "private.llm_traces" in connection.calls[0][0]


def test_usage_row_preserves_provider_reported_tokens() -> None:
    connection = RecordingConnection()
    sink = SupabaseLlmTraceSink(connection, game_id="game-1", request_id="request-1")

    sink.record_invocation(_trace(input_tokens=12, output_tokens=5, total_tokens=17))

    assert len(connection.calls) == 2
    assert "private.llm_usage" in connection.calls[1][0]
    parameters = connection.calls[1][1]
    assert isinstance(parameters, tuple)
    assert parameters[-2:] == (12, 5)
