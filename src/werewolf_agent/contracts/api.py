"""Allowlisted HTTP API contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from werewolf_agent.contracts.schemas import (
    GameSetupOptionsResponse,
    PlayerActionRequest,
    ProblemDetails,
)

OperationStatus = Literal["queued", "running", "succeeded", "failed"]
LlmMode = Literal["fake", "paid"]
RuntimeAvailability = Literal["available", "degraded", "unavailable"]


class PublicRuntimeLimits(BaseModel):
    """Required limits enforced by the HTTP API and rendered by clients."""

    game_min_players: int = Field(ge=1)
    game_max_players: int = Field(ge=1)
    message_max_chars: int = Field(ge=1)
    game_list_page_size: int = Field(ge=1)
    timeline_page_size: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicRuntimeFeatures(BaseModel):
    """Publicly discoverable feature switches."""

    authentication: bool
    paid_llm_for_members: bool
    admin_reveal: bool
    admin_replay: bool

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicRuntimeConfig(BaseModel):
    """Public runtime configuration shared by HTTP clients."""

    contract_version: str
    config_revision: str
    setup: GameSetupOptionsResponse
    limits: PublicRuntimeLimits
    features: PublicRuntimeFeatures

    model_config = ConfigDict(extra="forbid", frozen=True)


class SetupValidationResponse(BaseModel):
    """Normalized summary returned after semantic setup validation."""

    schema_version: int
    player_count: int = Field(ge=1)
    theme_id: str
    theme_name: str
    role_ids: tuple[str, ...]
    ability_ids: tuple[str, ...]
    setup_checksum: str
    mechanics_checksum: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeComponentStatus(BaseModel):
    """Sanitized availability for one runtime dependency."""

    component: Literal["api", "authentication", "database", "operation_queue"]
    status: RuntimeAvailability
    reason_code: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeStatusResponse(BaseModel):
    """Public dependency status used for client-side degradation."""

    status: RuntimeAvailability
    components: tuple[RuntimeComponentStatus, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)


class SessionResponse(BaseModel):
    """Allowlisted properties of the authenticated request principal."""

    authenticated: bool = True
    anonymous: bool
    administrator: bool
    llm_mode: LlmMode

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceOperationRequest(BaseModel):
    """Version-checked request for one game advance."""

    expected_version: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerActionOperationRequest(BaseModel):
    """Version-checked player action submitted to the queue."""

    player_id: str
    expected_version: int = Field(ge=1)
    action: PlayerActionRequest

    model_config = ConfigDict(extra="forbid", frozen=True)


class OperationResponse(BaseModel):
    """Public asynchronous operation state."""

    operation_id: str
    operation_type: str
    status: OperationStatus
    game_id: str | None = None
    expected_version: int | None = None
    result: dict[str, Any] | None = None
    error: ProblemDetails | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


class ReplayVerificationResponse(BaseModel):
    """Private-payload-free replay verification result."""

    game_id: str
    valid: bool
    checked_versions: int = Field(ge=0)
    first_mismatch_version: int | None = Field(default=None, ge=1)
    comparison_target: str | None = None
    expected_checksum: str | None = None
    actual_checksum: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdminOperationDiagnosticResponse(BaseModel):
    """Administrator-only operation metadata without request or owner data."""

    operation_id: str
    operation_type: str
    status: OperationStatus
    game_id: str | None = None
    attempt_count: int = Field(ge=0)
    worker_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: ProblemDetails | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdminLlmTraceResponse(BaseModel):
    """Administrator-only trace metadata with prompt content excluded."""

    invocation_id: str
    game_id: str
    operation_id: str | None = None
    state_version: int | None = Field(default=None, ge=1)
    provider: str
    model: str
    player_id: str | None = None
    phase: str | None = None
    day: int | None = None
    prompt_hash: str
    parsed_decision: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    latency_ms: float | None = Field(default=None, ge=0)
    created_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdminLlmTraceListResponse(BaseModel):
    """Bounded administrator trace page."""

    items: list[AdminLlmTraceResponse]

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdminLlmUsageResponse(BaseModel):
    """Aggregate administrator-only LLM usage."""

    game_id: str
    invocation_count: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_micros: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


__all__ = [
    "AdminLlmTraceListResponse",
    "AdminLlmTraceResponse",
    "AdminLlmUsageResponse",
    "AdminOperationDiagnosticResponse",
    "AdvanceOperationRequest",
    "LlmMode",
    "OperationResponse",
    "OperationStatus",
    "PlayerActionOperationRequest",
    "PublicRuntimeConfig",
    "PublicRuntimeFeatures",
    "PublicRuntimeLimits",
    "ReplayVerificationResponse",
    "RuntimeAvailability",
    "RuntimeComponentStatus",
    "RuntimeStatusResponse",
    "SessionResponse",
]
