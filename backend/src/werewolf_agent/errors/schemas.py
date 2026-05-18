"""Pydantic schemas for public error payloads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProblemIssue(BaseModel):
    """One validation issue in an RFC 9457 Problem Details response."""

    code: str
    detail: str
    pointer: str = ""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ProblemDetails(BaseModel):
    """RFC 9457 Problem Details response body with project extensions."""

    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str
    trace_id: str | None = None
    errors: list[ProblemIssue] | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class ErrorEventPayload(BaseModel):
    """Replay-safe JSONL payload for an application error event."""

    code: str
    detail: str
    retryable: bool
    context: dict[str, Any] | None = Field(default=None)

    model_config = ConfigDict(extra="forbid", frozen=True)
