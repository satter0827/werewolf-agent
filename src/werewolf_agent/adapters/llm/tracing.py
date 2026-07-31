"""Provider-independent LLM trace contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

USAGE_SOURCE_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class LlmInvocationTrace:
    """Replay-oriented trace for one LLM decision invocation."""

    provider: str
    model: str
    player_id: str
    phase: str
    day: int
    prompt_messages: list[Mapping[str, object]]
    prompt_hash: str
    prompt_version: int = 1
    setup_checksum: str = ""
    mechanics_checksum: str = ""
    observation_checksum: str = ""
    request_payload: Mapping[str, object] = field(default_factory=dict)
    raw_response: Mapping[str, object] | None = None
    parsed_decision: Mapping[str, object] | None = None
    error_payload: Mapping[str, object] | None = None
    latency_ms: float | None = None
    validation_status: str = ""
    fallback_used: bool = False
    fallback_reason: str = ""
    provider_error: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    usage_source: str = USAGE_SOURCE_UNAVAILABLE
    prompt_characters: int = 0
    prompt_bytes: int = 0
    response_characters: int = 0
    response_bytes: int = 0


class LlmTraceSink(Protocol):
    """Outer adapter boundary for durable LLM trace storage."""

    def record_invocation(self, trace: LlmInvocationTrace) -> None:
        """Record one invocation trace."""


class NullLlmTraceSink:
    """Trace sink used outside durable worker contexts."""

    def record_invocation(self, trace: LlmInvocationTrace) -> None:
        """Drop one invocation trace."""
        _ = trace
