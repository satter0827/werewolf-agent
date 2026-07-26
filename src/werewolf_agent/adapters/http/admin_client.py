"""Administrator-only HTTP client."""

from __future__ import annotations

import httpx

from werewolf_agent.adapters.http.base import HttpApiClient
from werewolf_agent.adapters.supabase.session_store import SupabaseSession
from werewolf_agent.contracts.api import (
    AdminLlmTraceListResponse,
    AdminLlmUsageResponse,
    AdminOperationDiagnosticResponse,
    ReplayVerificationResponse,
)
from werewolf_agent.contracts.schemas import GameRevealResponse
from werewolf_agent.settings import AppSettings


class HttpAdminClient:
    """Call only routes protected by administrator authorization."""

    def __init__(
        self,
        settings: AppSettings,
        session: SupabaseSession,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Create an administrator client with one verified session."""
        self._http = HttpApiClient(settings, session, transport=transport)

    def reveal_game(self, game_id: str) -> GameRevealResponse:
        """Return the authorized complete game state."""
        return self._http.model(
            GameRevealResponse,
            "GET",
            f"/api/v1/admin/games/{game_id}/reveal",
        )

    def verify_replay(self, game_id: str) -> ReplayVerificationResponse:
        """Verify deterministic replay without returning private state."""
        return self._http.model(
            ReplayVerificationResponse,
            "POST",
            f"/api/v1/admin/games/{game_id}/replay/verify",
        )

    def diagnose_operation(self, operation_id: str) -> AdminOperationDiagnosticResponse:
        """Return bounded worker diagnostics."""
        return self._http.model(
            AdminOperationDiagnosticResponse,
            "GET",
            f"/api/v1/admin/operations/{operation_id}",
        )

    def list_llm_traces(
        self,
        game_id: str,
        *,
        limit: int = 50,
    ) -> AdminLlmTraceListResponse:
        """Return redacted trace metadata."""
        return self._http.model(
            AdminLlmTraceListResponse,
            "GET",
            f"/api/v1/admin/games/{game_id}/llm-traces",
            params={"limit": limit},
        )

    def get_llm_usage(self, game_id: str) -> AdminLlmUsageResponse:
        """Return aggregate LLM usage."""
        return self._http.model(
            AdminLlmUsageResponse,
            "GET",
            f"/api/v1/admin/games/{game_id}/llm-usage",
        )


__all__ = ["HttpAdminClient"]
