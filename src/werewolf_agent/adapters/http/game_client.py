"""HTTP-only game client for Python clients."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import httpx

from werewolf_agent.adapters.http.base import HttpApiClient, parse_model
from werewolf_agent.adapters.supabase.session_store import SupabaseSession
from werewolf_agent.contracts import AppError, ErrorCode, ResourceNotFoundError
from werewolf_agent.contracts.api import (
    OperationResponse,
    PlayerActionOperationRequest,
    SessionResponse,
)
from werewolf_agent.contracts.schemas import (
    AdvanceGameJobResponse,
    AdvanceGameResponse,
    CreateGameRequest,
    GameListResponse,
    GameResponse,
    GameTimelineResponse,
    PlayerActionRequest,
    PlayerActionResponse,
    PlayerObservationResponse,
)
from werewolf_agent.settings import AppSettings


class HttpGameClient:
    """Call the versioned FastAPI contract with one Supabase access token."""

    def __init__(
        self,
        settings: AppSettings,
        session: SupabaseSession,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Create a reusable client without exposing the token to callers."""
        self._settings = settings
        self._http = HttpApiClient(
            settings,
            session,
            transport=transport,
        )
        self._latest_jobs: dict[str, str] = {}

    def get_session(self) -> SessionResponse:
        """Return the current authenticated session capabilities."""
        return self._http.model(SessionResponse, "GET", "/api/v1/session")

    def create_game(self, request: CreateGameRequest) -> GameResponse:
        """Create a game and wait for its asynchronous operation."""
        operation = self._command(
            "/api/v1/games",
            request.model_dump(mode="json", exclude_none=True),
        )
        completed = self._wait(operation)
        if completed.result is None:
            raise AppError("ゲーム作成結果がありません。", code=ErrorCode.INTERNAL_UNEXPECTED)
        return parse_model(GameResponse, completed.result)

    def get_game(self, game_id: str) -> GameResponse:
        """Return one authorized public game projection."""
        return self._http.model(GameResponse, "GET", f"/api/v1/games/{game_id}")

    def list_games(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> GameListResponse:
        """Return one authorized page of game summaries."""
        params: dict[str, Any] = {"offset": offset}
        if status is not None:
            params["status"] = status
        if limit is not None:
            params["limit"] = limit
        return self._http.model(
            GameListResponse,
            "GET",
            "/api/v1/games",
            params=params,
        )

    def advance_game(self, game_id: str) -> AdvanceGameResponse:
        """Advance a game and wait for its asynchronous operation."""
        game = self.get_game(game_id)
        operation = self._command(
            f"/api/v1/games/{game_id}/advance",
            {"expected_version": game.state.version},
        )
        self._latest_jobs[game_id] = operation.operation_id
        completed = self._wait(operation)
        if completed.result is None:
            raise AppError("進行結果がありません。", code=ErrorCode.INTERNAL_UNEXPECTED)
        return parse_model(AdvanceGameResponse, completed.result)

    def start_advance_game(self, game_id: str) -> AdvanceGameJobResponse:
        """Queue a game advance and return its job state."""
        game = self.get_game(game_id)
        operation = self._command(
            f"/api/v1/games/{game_id}/advance",
            {"expected_version": game.state.version},
        )
        self._latest_jobs[game_id] = operation.operation_id
        return _job(operation)

    def get_advance_job(self, game_id: str, job_id: str) -> AdvanceGameJobResponse:
        """Return one owned advance job."""
        operation = self._http.model(
            OperationResponse,
            "GET",
            f"/api/v1/operations/{job_id}",
        )
        if operation.game_id not in (None, game_id):
            raise ResourceNotFoundError("操作が見つかりません。")
        return _job(operation)

    def get_latest_advance_job(self, game_id: str) -> AdvanceGameJobResponse:
        """Return the latest advance job started by this client."""
        job_id = self._latest_jobs.get(game_id)
        if job_id is None:
            raise ResourceNotFoundError("操作が見つかりません。")
        return self.get_advance_job(game_id, job_id)

    def get_timeline(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int | None = None,
    ) -> GameTimelineResponse:
        """Return public timeline items after a cursor."""
        params: dict[str, Any] = {"after": after}
        if limit is not None:
            params["limit"] = limit
        return self._http.model(
            GameTimelineResponse,
            "GET",
            f"/api/v1/games/{game_id}/timeline",
            params=params,
        )

    def get_private_observation(
        self,
        game_id: str,
        player_id: str,
    ) -> PlayerObservationResponse:
        """Return one authorized player's private observation."""
        return self._http.model(
            PlayerObservationResponse,
            "GET",
            f"/api/v1/games/{game_id}/observation/{player_id}",
        )

    def submit_player_action(
        self,
        game_id: str,
        player_id: str,
        request: PlayerActionRequest,
    ) -> PlayerActionResponse:
        """Submit a version-checked player action and await completion."""
        game = self.get_game(game_id)
        body = PlayerActionOperationRequest(
            player_id=player_id,
            expected_version=game.state.version,
            action=request,
        )
        operation = self._command(
            f"/api/v1/games/{game_id}/actions",
            body.model_dump(mode="json", exclude_none=True),
        )
        completed = self._wait(operation)
        if completed.result is None:
            raise AppError("行動結果がありません。", code=ErrorCode.INTERNAL_UNEXPECTED)
        return parse_model(PlayerActionResponse, completed.result)

    def _command(self, path: str, body: dict[str, Any]) -> OperationResponse:
        return self._http.model(
            OperationResponse,
            "POST",
            path,
            json=body,
            headers={"Idempotency-Key": str(uuid4())},
        )

    def _wait(self, operation: OperationResponse) -> OperationResponse:
        deadline = time.monotonic() + self._settings.advance_job_poll_timeout_seconds
        current = operation
        while current.status not in {"succeeded", "failed"}:
            if time.monotonic() >= deadline:
                raise AppError(
                    "操作が時間内に完了しませんでした。",
                    code=ErrorCode.API_UNAVAILABLE,
                    retryable=True,
                )
            time.sleep(self._settings.advance_job_poll_interval_seconds)
            current = self._http.model(
                OperationResponse,
                "GET",
                f"/api/v1/operations/{current.operation_id}",
            )
        if current.status == "failed":
            detail = current.error.detail if current.error else "操作に失敗しました。"
            raise AppError(detail, code=ErrorCode.INTERNAL_UNEXPECTED)
        return current


def _job(operation: OperationResponse) -> AdvanceGameJobResponse:
    result = parse_model(AdvanceGameResponse, operation.result) if operation.result else None
    status = {
        "queued": "queued",
        "running": "running",
        "succeeded": "completed",
        "failed": "failed",
    }[operation.status]
    version = operation.expected_version or 1
    if result is not None:
        version = result.state.version
    return AdvanceGameJobResponse(
        job_id=operation.operation_id,
        game_id=operation.game_id or "",
        status=status,  # type: ignore[arg-type]
        state_version=version,
        result=result,
        error=operation.error,
        created_at=operation.created_at,
        started_at=None,
        completed_at=operation.updated_at if operation.status in {"succeeded", "failed"} else None,
        updated_at=operation.updated_at,
    )


__all__ = ["HttpGameClient"]
