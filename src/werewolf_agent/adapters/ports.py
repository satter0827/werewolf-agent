"""Minimal protocols shared by user clients."""

from __future__ import annotations

from typing import Protocol

from werewolf_agent.contracts.api import (
    AdminLlmTraceListResponse,
    AdminLlmUsageResponse,
    AdminOperationDiagnosticResponse,
    PlayerPreviewRequest,
    PlayerPreviewResponse,
    PublicRuntimeConfig,
    ReplayVerificationResponse,
    RuntimeStatusResponse,
    SavedSetupListResponse,
    SavedSetupRevisionResponse,
    SessionResponse,
    SetupCatalogResponse,
    SetupCreateRequest,
    SetupRevisionCreateRequest,
    SetupTemplateResponse,
    SetupValidationResponse,
)
from werewolf_agent.contracts.schemas import (
    AdvanceGameJobResponse,
    AdvanceGameResponse,
    CreateGameRequest,
    GameListResponse,
    GameResponse,
    GameRevealResponse,
    GameSetupDocumentRequest,
    GameTimelineResponse,
    PlayerActionRequest,
    PlayerActionResponse,
    PlayerObservationResponse,
)


class PublicClient(Protocol):
    """Operations available before authentication."""

    def health(self) -> dict[str, str]:
        """Return process liveness."""
        ...

    def get_runtime_config(self) -> PublicRuntimeConfig:
        """Return public runtime configuration."""
        ...

    def get_runtime_status(self) -> RuntimeStatusResponse:
        """Return safe dependency availability."""
        ...

    def validate_setup(self, setup: GameSetupDocumentRequest) -> SetupValidationResponse:
        """Validate a complete setup without creating a game."""
        ...

    def get_setup_catalog(self) -> SetupCatalogResponse:
        """Return packaged setup metadata for public editors."""
        ...

    def get_setup_template(self, template_id: str) -> SetupTemplateResponse:
        """Return one complete packaged setup template."""
        ...

    def preview_players(self, request: PlayerPreviewRequest) -> PlayerPreviewResponse:
        """Return a public deterministic player preview."""
        ...


class GameClient(Protocol):
    """Authenticated game operations used by human-facing entry points."""

    def get_session(self) -> SessionResponse:
        """Return safe capabilities of the current session."""
        ...

    def list_setups(self) -> SavedSetupListResponse:
        """Return setup summaries owned by the current user."""
        ...

    def create_setup(self, request: SetupCreateRequest) -> SavedSetupRevisionResponse:
        """Create an owned setup and its first revision."""
        ...

    def get_setup(self, setup_id: str) -> SavedSetupRevisionResponse:
        """Return the latest revision of an owned setup."""
        ...

    def get_setup_revision(self, setup_id: str, revision: int) -> SavedSetupRevisionResponse:
        """Return one immutable owned setup revision."""
        ...

    def list_setup_revisions(self, setup_id: str) -> list[SavedSetupRevisionResponse]:
        """Return revision history for an owned setup."""
        ...

    def create_setup_revision(
        self, setup_id: str, request: SetupRevisionCreateRequest
    ) -> SavedSetupRevisionResponse:
        """Append one immutable revision to an owned setup."""
        ...

    def create_game(self, request: CreateGameRequest) -> GameResponse:
        """Create one game and await its operation."""
        ...

    def get_game(self, game_id: str) -> GameResponse:
        """Return one authorized public game projection."""
        ...

    def list_games(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> GameListResponse:
        """Return one authorized page of games."""
        ...

    def advance_game(self, game_id: str) -> AdvanceGameResponse:
        """Advance one game and await its operation."""
        ...

    def start_advance_game(self, game_id: str) -> AdvanceGameJobResponse:
        """Start one game advance operation."""
        ...

    def get_advance_job(self, game_id: str, job_id: str) -> AdvanceGameJobResponse:
        """Return one advance operation owned by the game."""
        ...

    def get_latest_advance_job(self, game_id: str) -> AdvanceGameJobResponse:
        """Return the latest locally started advance operation."""
        ...

    def get_timeline(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int | None = None,
    ) -> GameTimelineResponse:
        """Return public timeline items after a cursor."""
        ...

    def get_private_observation(
        self,
        game_id: str,
        player_id: str,
    ) -> PlayerObservationResponse:
        """Return one authorized player's private observation."""
        ...

    def submit_player_action(
        self,
        game_id: str,
        player_id: str,
        request: PlayerActionRequest,
    ) -> PlayerActionResponse:
        """Submit one authorized manual-player action."""
        ...


class AdminClient(Protocol):
    """Administrator-only diagnostics and reveal operations."""

    def reveal_game(self, game_id: str) -> GameRevealResponse:
        """Return the authorized complete game state."""
        ...

    def verify_replay(self, game_id: str) -> ReplayVerificationResponse:
        """Verify deterministic replay for one game."""
        ...

    def diagnose_operation(self, operation_id: str) -> AdminOperationDiagnosticResponse:
        """Return bounded operation diagnostics."""
        ...

    def list_llm_traces(
        self,
        game_id: str,
        *,
        limit: int = 50,
    ) -> AdminLlmTraceListResponse:
        """Return redacted LLM trace metadata."""
        ...

    def get_llm_usage(self, game_id: str) -> AdminLlmUsageResponse:
        """Return aggregate LLM usage for one game."""
        ...


__all__ = ["AdminClient", "GameClient", "PublicClient"]
