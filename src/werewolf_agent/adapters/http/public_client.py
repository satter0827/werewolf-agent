"""Unauthenticated runtime client."""

from __future__ import annotations

import httpx
from pydantic import BaseModel, ConfigDict

from werewolf_agent.adapters.http.base import HttpApiClient
from werewolf_agent.contracts.api import (
    PublicRuntimeConfig,
    RuntimeStatusResponse,
    SetupValidationResponse,
)
from werewolf_agent.contracts.schemas import GameSetupDocumentRequest
from werewolf_agent.settings import AppSettings


class _HealthResponse(BaseModel):
    status: str
    service: str
    instance_id: str
    started_at: str
    config_fingerprint: str

    model_config = ConfigDict(extra="ignore")


class HttpPublicClient:
    """Read runtime metadata without requiring a Supabase session."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Create an unauthenticated runtime client."""
        self._http = HttpApiClient(settings, transport=transport)

    def health(self) -> dict[str, str]:
        """Return API process liveness."""
        return self._http.model(_HealthResponse, "GET", "/health").model_dump()

    def get_runtime_config(self) -> PublicRuntimeConfig:
        """Return public runtime configuration."""
        return self._http.model(PublicRuntimeConfig, "GET", "/api/v1/config")

    def get_runtime_status(self) -> RuntimeStatusResponse:
        """Return sanitized dependency availability."""
        return self._http.model(RuntimeStatusResponse, "GET", "/api/v1/status")

    def validate_setup(self, setup: GameSetupDocumentRequest) -> SetupValidationResponse:
        """Validate a complete setup through the canonical application boundary."""
        return self._http.model(
            SetupValidationResponse,
            "POST",
            "/api/v1/setups/validate",
            json=setup.model_dump(mode="json"),
        )


__all__ = ["HttpPublicClient"]
