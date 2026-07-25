"""Minimal client protocol shared by user interfaces."""

from __future__ import annotations

from typing import Protocol

from werewolf_agent.contracts.api import PublicRuntimeConfig
from werewolf_agent.contracts.schemas import (
    AdvanceGameJobResponse,
    AdvanceGameResponse,
    CreateGameRequest,
    GameListResponse,
    GameResponse,
    GameSetupOptionsResponse,
    GameTimelineResponse,
    PlayerActionRequest,
    PlayerActionResponse,
    PlayerObservationResponse,
)


class GameClient(Protocol):
    """Operations needed by human-facing entry points."""

    def health(self) -> dict[str, str]:
        """Return backing service health."""

    def get_runtime_config(self) -> PublicRuntimeConfig:
        """Return the API-owned public runtime configuration."""

    def get_setup_options(self) -> GameSetupOptionsResponse:
        """Return game setup options."""

    def create_game(self, request: CreateGameRequest) -> GameResponse:
        """Create one game."""

    def get_game(self, game_id: str) -> GameResponse:
        """Fetch one game."""

    def list_games(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> GameListResponse:
        """Return visible game summaries."""

    def advance_game(self, game_id: str) -> AdvanceGameResponse:
        """Advance one game, waiting for queue completion when needed."""

    def start_advance_game(self, game_id: str) -> AdvanceGameJobResponse:
        """Queue one advance request."""

    def get_advance_job(self, game_id: str, job_id: str) -> AdvanceGameJobResponse:
        """Fetch one queued operation as a job."""

    def get_latest_advance_job(self, game_id: str) -> AdvanceGameJobResponse:
        """Fetch the latest queued operation for a game."""

    def get_timeline(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int | None = None,
    ) -> GameTimelineResponse:
        """Fetch public timeline items."""

    def get_private_observation(
        self,
        game_id: str,
        player_id: str,
    ) -> PlayerObservationResponse:
        """Fetch private observation visible to a player."""

    def submit_player_action(
        self,
        game_id: str,
        player_id: str,
        request: PlayerActionRequest,
    ) -> PlayerActionResponse:
        """Submit one manual player action."""
