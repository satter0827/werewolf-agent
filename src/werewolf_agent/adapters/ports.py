"""Minimal protocols shared by user clients."""

from __future__ import annotations

from typing import Protocol

from werewolf_agent.contracts.api import (
    AdminLlmTraceListResponse,
    AdminLlmUsageResponse,
    AdminOperationDiagnosticResponse,
    PublicRuntimeConfig,
    ReplayVerificationResponse,
    RuntimeStatusResponse,
    SessionResponse,
)
from werewolf_agent.contracts.schemas import (
    AdvanceGameJobResponse,
    AdvanceGameResponse,
    CreateGameRequest,
    GameListResponse,
    GameResponse,
    GameRevealResponse,
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


class GameClient(Protocol):
    """Authenticated game operations used by human-facing entry points."""

    def get_session(self) -> SessionResponse:
        """Return safe capabilities of the current session."""
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
