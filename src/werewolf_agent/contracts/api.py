"""Allowlisted HTTP API contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from werewolf_agent.contracts.schemas import (
    GameSetupDocumentRequest,
    GameSetupSelectionRequest,
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

    config_revision: str
    limits: PublicRuntimeLimits
    features: PublicRuntimeFeatures

    model_config = ConfigDict(extra="forbid", frozen=True)


class SetupValidationResponse(BaseModel):
    """Normalized summary returned after semantic setup validation."""

    schema_version: str
    player_count: int = Field(ge=1)
    theme_id: str
    theme_name: str
    role_ids: tuple[str, ...]
    ability_ids: tuple[str, ...]
    setup_checksum: str
    mechanics_checksum: str
    warnings: tuple[str, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True)


class SetupCatalogResponse(BaseModel):
    """Public editor metadata and packaged template summaries."""

    player_count: dict[str, int]
    recommended_template_id: str
    template_order: tuple[str, ...]
    templates: dict[str, dict[str, str]]
    ability_kinds: tuple[str, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)


class SetupTemplateResponse(BaseModel):
    """One complete packaged setup template."""

    template_id: str
    document: GameSetupDocumentRequest

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerPreviewRequest(BaseModel):
    """Request for deterministic public player generation."""

    setup: GameSetupSelectionRequest
    seed: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicGeneratedPlayer(BaseModel):
    """Generated player fields safe to expose before game creation."""

    player_id: str
    name: str
    age: int
    gender: str
    personality: str
    speaking_style: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerPreviewResponse(BaseModel):
    """Deterministic public roster preview and checksum."""

    seed: int
    players: tuple[PublicGeneratedPlayer, ...]
    roster_checksum: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class SetupCreateRequest(BaseModel):
    """Request to persist the first revision of a user setup."""

    display_name: str = Field(min_length=1, max_length=120)
    document: GameSetupDocumentRequest

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SetupRevisionCreateRequest(BaseModel):
    """Optimistic request to append an immutable setup revision."""

    expected_revision: int = Field(ge=1)
    document: GameSetupDocumentRequest

    model_config = ConfigDict(extra="forbid", frozen=True)


class SavedSetupSummaryResponse(BaseModel):
    """Owned setup summary with its latest revision number."""

    setup_id: str
    display_name: str
    latest_revision: int
    created_at: datetime
    updated_at: datetime


class SavedSetupRevisionResponse(BaseModel):
    """One complete immutable owned setup revision."""

    setup_id: str
    display_name: str
    revision: int
    document: GameSetupDocumentRequest
    setup_checksum: str
    mechanics_checksum: str
    created_at: datetime


class SavedSetupListResponse(BaseModel):
    """Owned setup summaries visible to the current user."""

    items: list[SavedSetupSummaryResponse]


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
    "PlayerPreviewRequest",
    "PlayerPreviewResponse",
    "PublicGeneratedPlayer",
    "PublicRuntimeConfig",
    "PublicRuntimeFeatures",
    "PublicRuntimeLimits",
    "ReplayVerificationResponse",
    "RuntimeAvailability",
    "RuntimeComponentStatus",
    "RuntimeStatusResponse",
    "SavedSetupListResponse",
    "SavedSetupRevisionResponse",
    "SavedSetupSummaryResponse",
    "SessionResponse",
    "SetupCatalogResponse",
    "SetupCreateRequest",
    "SetupRevisionCreateRequest",
    "SetupTemplateResponse",
    "SetupValidationResponse",
]
