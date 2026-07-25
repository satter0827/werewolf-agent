"""HTTP-only game client for Python clients."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from werewolf_agent.adapters.supabase.session_store import SupabaseSession
from werewolf_agent.contracts import AppError, ErrorCode, ResourceNotFoundError
from werewolf_agent.contracts.api import (
    OperationResponse,
    PlayerActionOperationRequest,
    PublicRuntimeConfig,
)
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
    ProblemDetails,
)
from werewolf_agent.settings import AppSettings

TModel = TypeVar("TModel", bound=BaseModel)


class _HealthResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str
    service: str


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
        self._session = session
        self._client = httpx.Client(
            base_url=settings.api_base_url.rstrip("/"),
            timeout=settings.api_timeout_seconds,
            transport=transport,
            headers={"Authorization": f"Bearer {session.access_token}"},
        )
        self._latest_jobs: dict[str, str] = {}

    def health(self) -> dict[str, str]:
        """Return the API process health status."""
        return self._model(_HealthResponse, "GET", "/health").model_dump()

    def get_runtime_config(self) -> PublicRuntimeConfig:
        """Return the API-owned public runtime configuration."""
        return self._model(
            PublicRuntimeConfig,
            "GET",
            "/api/v1/config",
            authenticated=False,
        )

    def get_setup_options(self) -> GameSetupOptionsResponse:
        """Return server-validated game setup options."""
        return self.get_runtime_config().setup

    def create_game(self, request: CreateGameRequest) -> GameResponse:
        """Create a game and wait for its asynchronous operation."""
        operation = self._command(
            "/api/v1/games",
            request.model_dump(mode="json", exclude_none=True),
        )
        completed = self._wait(operation)
        if completed.result is None:
            raise AppError("ゲーム作成結果がありません。", code=ErrorCode.INTERNAL_UNEXPECTED)
        return _parse(GameResponse, completed.result)

    def get_game(self, game_id: str) -> GameResponse:
        """Return one authorized public game projection."""
        return self._model(GameResponse, "GET", f"/api/v1/games/{game_id}")

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
        return self._model(GameListResponse, "GET", "/api/v1/games", params=params)

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
        return _parse(AdvanceGameResponse, completed.result)

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
        operation = self._model(
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
        return self._model(
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
        return self._model(
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
        return _parse(PlayerActionResponse, completed.result)

    def _command(self, path: str, body: dict[str, Any]) -> OperationResponse:
        return self._model(
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
            current = self._model(
                OperationResponse,
                "GET",
                f"/api/v1/operations/{current.operation_id}",
            )
        if current.status == "failed":
            detail = current.error.detail if current.error else "操作に失敗しました。"
            raise AppError(detail, code=ErrorCode.INTERNAL_UNEXPECTED)
        return current

    def _model(
        self,
        model_type: type[TModel],
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        **kwargs: Any,
    ) -> TModel:
        headers = dict(kwargs.pop("headers", {}))
        if not authenticated:
            headers["Authorization"] = ""
        try:
            response = self._client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise AppError(
                "APIへ接続できませんでした。",
                code=ErrorCode.API_UNAVAILABLE,
                retryable=True,
            ) from exc
        if response.is_error:
            _raise_problem(response)
        try:
            return model_type.model_validate(response.json())
        except (ValidationError, ValueError) as exc:
            raise AppError(
                "API応答の形式を確認できませんでした。",
                code=ErrorCode.INTERNAL_UNEXPECTED,
            ) from exc


def _job(operation: OperationResponse) -> AdvanceGameJobResponse:
    result = _parse(AdvanceGameResponse, operation.result) if operation.result else None
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


def _parse(model_type: type[TModel], payload: Any) -> TModel:
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise AppError(
            "API応答の形式を確認できませんでした。",
            code=ErrorCode.INTERNAL_UNEXPECTED,
        ) from exc


def _raise_problem(response: httpx.Response) -> None:
    try:
        problem = ProblemDetails.model_validate(response.json())
    except (ValidationError, ValueError) as exc:
        raise AppError(
            "API要求に失敗しました。",
            code=ErrorCode.API_UNAVAILABLE,
        ) from exc
    code = (
        ErrorCode(problem.code)
        if problem.code in {item.value for item in ErrorCode}
        else ErrorCode.INTERNAL_UNEXPECTED
    )
    raise AppError(problem.detail, code=code)


def _now() -> datetime:
    return datetime.now(UTC)


__all__ = ["HttpGameClient"]
