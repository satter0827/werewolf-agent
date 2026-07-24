"""Supabase Data API client for user interfaces."""

from __future__ import annotations

import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from werewolf_agent.adapters.supabase.session_store import SupabaseSession
from werewolf_agent.configuration import AppSettings
from werewolf_agent.configuration.messages import (
    DETAIL_RESOURCE_NOT_FOUND,
    MESSAGE_ADVANCE_REQUEST_FAILED,
    MESSAGE_ADVANCE_REQUEST_RESULT_MISSING,
    MESSAGE_ADVANCE_REQUEST_TIMED_OUT,
    MESSAGE_COMPLETED_OPERATION_RESULT_MISSING,
    MESSAGE_OPERATION_REQUEST_CANCELLED,
    MESSAGE_OPERATION_REQUEST_FAILED,
    MESSAGE_OPERATION_REQUEST_TIMED_OUT,
    MESSAGE_SUPABASE_DATA_API_NON_LIST_RESPONSE,
    MESSAGE_SUPABASE_DATA_API_UNAVAILABLE,
    MESSAGE_SUPABASE_GAME_REVEAL_NOT_FOUND,
    MESSAGE_SUPABASE_OPERATION_NOT_RETURNED,
    message_supabase_data_api_http_error,
    message_supabase_payload_schema_mismatch,
)
from werewolf_agent.contracts import AppError, ResourceNotFoundError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    ADVANCE_JOB_STATUS_COMPLETED,
    ADVANCE_JOB_STATUS_FAILED,
    AdvanceGameJobResponse,
    AdvanceGameResponse,
    AdvanceJobStatus,
    CreateGameRequest,
    GameListResponse,
    GameResponse,
    GameRevealResponse,
    GameSetupOptionsResponse,
    GameTimelineItem,
    GameTimelineResponse,
    PlayerActionRequest,
    PlayerActionResponse,
    PlayerObservationResponse,
    ProblemDetails,
    PublicGameState,
    PublicGameSummary,
)

TModel = TypeVar("TModel", bound=BaseModel)
QUEUE_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class SupabaseGameClient:
    """Direct Data API client using a user's Supabase JWT."""

    def __init__(
        self,
        settings: AppSettings,
        session: SupabaseSession,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Create a client for one authenticated user."""
        self._settings = settings
        self._session = session
        self._base_url = settings.supabase_url.rstrip("/")
        self._client = httpx.Client(
            timeout=settings.supabase_rest_timeout_seconds,
            transport=transport,
        )

    def health(self) -> dict[str, str]:
        """Return Supabase Data API health."""
        self._request_json(
            "GET",
            "game_summaries",
            params={"select": "game_id", "limit": "1"},
        )
        return {"status": "ok", "service": "supabase"}

    def get_setup_options(self) -> GameSetupOptionsResponse:
        """Return setup options published through Supabase."""
        row = self._single_row(
            "definition_items",
            params={
                "select": "payload",
                "scope": "eq.system",
                "kind": "eq.setup_options",
                "item_key": "eq.default",
                "active": "is.true",
                "limit": "1",
            },
        )
        return _parse_model(GameSetupOptionsResponse, row.get("payload"))

    def create_game(self, request: CreateGameRequest) -> GameResponse:
        """Queue one game creation request and wait for worker completion."""
        row = self._insert_operation(
            operation_type="create_game",
            payload=request.model_dump(mode="json", exclude_none=True, exclude_defaults=True),
        )
        completed = self._wait_for_request(str(row["request_id"]))
        payload = _result_payload(completed)
        return _parse_model(GameResponse, payload)

    def get_game(self, game_id: str) -> GameResponse:
        """Fetch one visible game."""
        row = self._single_row(
            "games",
            params={
                "select": "game_id,public_state",
                "game_id": f"eq.{game_id}",
                "limit": "1",
            },
        )
        state = PublicGameState.model_validate(row["public_state"])
        return GameResponse(game_id=str(row["game_id"]), state=state)

    def get_game_reveal(self, game_id: str) -> GameRevealResponse:
        """Fetch admin-only reveal information."""
        row = self._single_row(
            "game_reveals",
            params={
                "select": "reveal_payload",
                "game_id": f"eq.{game_id}",
                "limit": "1",
            },
        )
        payload = row.get("reveal_payload")
        if not isinstance(payload, dict):
            raise ResourceNotFoundError(MESSAGE_SUPABASE_GAME_REVEAL_NOT_FOUND)
        return _parse_model(GameRevealResponse, payload)

    def list_games(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> GameListResponse:
        """Return visible game summaries."""
        resolved_limit = limit or self._settings.api_game_list_default_limit
        params: dict[str, str] = {
            "select": "*",
            "order": "updated_at.desc,created_at.desc",
            "limit": str(resolved_limit),
            "offset": str(offset),
        }
        if status is not None:
            params["status"] = f"eq.{status}"
        rows = self._request_rows("game_summaries", params=params)
        summaries = [_summary_from_row(row) for row in rows]
        next_offset = offset + resolved_limit if len(summaries) == resolved_limit else None
        return GameListResponse(games=summaries, next_offset=next_offset)

    def advance_game(self, game_id: str) -> AdvanceGameResponse:
        """Queue one advance request and wait for worker completion."""
        job = self.start_advance_game(game_id)
        deadline = time.perf_counter() + self._settings.advance_job_poll_timeout_seconds
        while True:
            if job.status == ADVANCE_JOB_STATUS_COMPLETED:
                if job.result is None:
                    raise AppError(MESSAGE_ADVANCE_REQUEST_RESULT_MISSING)
                return job.result
            if job.status == ADVANCE_JOB_STATUS_FAILED:
                if job.error is not None:
                    raise AppError(job.error.detail, code=ErrorCode.INTERNAL_UNEXPECTED)
                raise AppError(MESSAGE_ADVANCE_REQUEST_FAILED)
            if time.perf_counter() >= deadline:
                raise AppError(
                    MESSAGE_ADVANCE_REQUEST_TIMED_OUT,
                    code=ErrorCode.API_UNAVAILABLE,
                    retryable=True,
                )
            time.sleep(self._settings.advance_job_poll_interval_seconds)
            job = self.get_advance_job(game_id, job.job_id)

    def start_advance_game(self, game_id: str) -> AdvanceGameJobResponse:
        """Queue one advance request."""
        row = self._insert_operation(
            operation_type="advance_game",
            payload={},
            game_id=game_id,
        )
        return _job_from_row(row)

    def get_advance_job(self, game_id: str, job_id: str) -> AdvanceGameJobResponse:
        """Fetch a queued operation as a job."""
        row = self._single_row(
            "game_operation_requests",
            params={
                "select": "*",
                "request_id": f"eq.{job_id}",
                "game_id": f"eq.{game_id}",
                "limit": "1",
            },
        )
        return _job_from_row(row)

    def get_latest_advance_job(self, game_id: str) -> AdvanceGameJobResponse:
        """Fetch the latest queued advance operation for a game."""
        row = self._single_row(
            "game_operation_requests",
            params={
                "select": "*",
                "operation_type": "eq.advance_game",
                "game_id": f"eq.{game_id}",
                "order": "created_at.desc",
                "limit": "1",
            },
        )
        return _job_from_row(row)

    def get_timeline(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int | None = None,
    ) -> GameTimelineResponse:
        """Fetch public timeline items."""
        resolved_limit = limit or self._settings.api_timeline_default_limit
        rows = self._request_rows(
            "game_public_turns",
            params={
                "select": "*",
                "game_id": f"eq.{game_id}",
                "sequence": f"gt.{after}",
                "order": "sequence.asc",
                "limit": str(resolved_limit),
            },
        )
        items = [_timeline_item_from_row(row) for row in rows]
        next_after = items[-1].sequence if items else after
        return GameTimelineResponse(game_id=game_id, items=items, next_after=next_after)

    def get_private_observation(
        self,
        game_id: str,
        player_id: str,
    ) -> PlayerObservationResponse:
        """Fetch private observation visible through RLS."""
        row = self._single_row(
            "game_player_observations",
            params={
                "select": "game_id,player_id,observation",
                "game_id": f"eq.{game_id}",
                "player_id": f"eq.{player_id}",
                "limit": "1",
            },
        )
        return PlayerObservationResponse(
            game_id=str(row["game_id"]),
            player_id=str(row["player_id"]),
            observation=_json_object(row.get("observation")),
        )

    def submit_player_action(
        self,
        game_id: str,
        player_id: str,
        request: PlayerActionRequest,
    ) -> PlayerActionResponse:
        """Queue one player action and wait for completion."""
        row = self._insert_operation(
            operation_type="submit_action",
            game_id=game_id,
            player_id=player_id,
            payload=request.model_dump(mode="json", exclude_none=True),
        )
        completed = self._wait_for_request(str(row["request_id"]))
        return _parse_model(PlayerActionResponse, _result_payload(completed))

    def _wait_for_request(self, request_id: str) -> dict[str, Any]:
        deadline = time.perf_counter() + self._settings.advance_job_poll_timeout_seconds
        while True:
            row = self._single_row(
                "game_operation_requests",
                params={"select": "*", "request_id": f"eq.{request_id}", "limit": "1"},
            )
            status = str(row.get("status") or "")
            if status in QUEUE_TERMINAL_STATUSES:
                if status == "failed":
                    raise AppError(_queue_error_detail(row), code=ErrorCode.INTERNAL_UNEXPECTED)
                if status == "cancelled":
                    raise AppError(MESSAGE_OPERATION_REQUEST_CANCELLED)
                return row
            if time.perf_counter() >= deadline:
                raise AppError(
                    MESSAGE_OPERATION_REQUEST_TIMED_OUT,
                    code=ErrorCode.API_UNAVAILABLE,
                    retryable=True,
                )
            time.sleep(self._settings.advance_job_poll_interval_seconds)

    def _insert_operation(
        self,
        *,
        operation_type: str,
        payload: Mapping[str, Any],
        game_id: str | None = None,
        player_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "operation_type": operation_type,
            "request_payload": dict(payload),
        }
        if game_id is not None:
            body["game_id"] = game_id
        if player_id is not None:
            body["player_id"] = player_id
        rows = self._request_rows(
            "game_operation_requests",
            method="POST",
            body=body,
            headers={"Prefer": "return=representation"},
        )
        if not rows:
            raise AppError(MESSAGE_SUPABASE_OPERATION_NOT_RETURNED)
        return rows[0]

    def _single_row(self, table: str, *, params: Mapping[str, str]) -> dict[str, Any]:
        rows = self._request_rows(table, params=params)
        if not rows:
            raise ResourceNotFoundError(DETAIL_RESOURCE_NOT_FOUND)
        return rows[0]

    def _request_rows(
        self,
        table: str,
        *,
        method: str = "GET",
        params: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        payload = self._request_json(method, table, params=params, body=body, headers=headers)
        if not isinstance(payload, list):
            raise AppError(MESSAGE_SUPABASE_DATA_API_NON_LIST_RESPONSE)
        return [dict(item) for item in payload if isinstance(item, dict)]

    def _request_json(
        self,
        method: str,
        table: str,
        *,
        params: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        request_headers = {
            "apikey": self._settings.supabase_publishable_key_value,
            "Authorization": f"Bearer {self._session.access_token}",
            "Content-Type": "application/json",
            **dict(headers or {}),
        }
        try:
            response = self._client.request(
                method,
                f"{self._base_url}/rest/v1/{table}",
                params=params,
                json=body,
                headers=request_headers,
            )
            response.raise_for_status()
            return response.json() if response.content else []
        except httpx.HTTPStatusError as exc:
            raise AppError(
                _supabase_error_detail(exc.response),
                code=ErrorCode.API_UNAVAILABLE,
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise AppError(
                MESSAGE_SUPABASE_DATA_API_UNAVAILABLE,
                code=ErrorCode.API_UNAVAILABLE,
                retryable=True,
            ) from exc


def _summary_from_row(row: Mapping[str, Any]) -> PublicGameSummary:
    return PublicGameSummary.model_validate(row)


def _timeline_item_from_row(row: Mapping[str, Any]) -> GameTimelineItem:
    return GameTimelineItem.model_validate(
        {
            "sequence": row["sequence"],
            "event_sequence": row["event_sequence"],
            "version": row["version"],
            "phase": row.get("phase"),
            "day": row.get("day"),
            "actor_id": row.get("actor_id"),
            "event_type": row["event_type"],
            "payload": _json_object(row.get("payload")),
            "occurred_at": row["occurred_at"],
        }
    )


def _job_from_row(row: Mapping[str, Any]) -> AdvanceGameJobResponse:
    result_payload = row.get("result_payload")
    error_payload = row.get("error_payload")
    result = (
        _parse_model(AdvanceGameResponse, result_payload)
        if isinstance(result_payload, dict)
        else None
    )
    error = _parse_model(ProblemDetails, error_payload) if isinstance(error_payload, dict) else None
    status = str(row.get("status") or "queued")
    status_map: dict[str, AdvanceJobStatus] = {
        "queued": "queued",
        "running": "running",
        "completed": "completed",
        "failed": "failed",
        "cancelled": "failed",
    }
    job_status = status_map.get(status, "failed")
    state_version = 1
    if result is not None:
        state_version = result.state.version
    return AdvanceGameJobResponse(
        job_id=str(row["request_id"]),
        game_id=str(row.get("game_id") or ""),
        status=job_status,
        state_version=state_version,
        result=result,
        error=error,
        created_at=_datetime_field(row, "created_at"),
        started_at=_optional_datetime_field(row, "started_at"),
        completed_at=_optional_datetime_field(row, "completed_at"),
        updated_at=_datetime_field(row, "updated_at"),
    )


def _result_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = row.get("result_payload")
    if not isinstance(payload, dict):
        raise AppError(MESSAGE_COMPLETED_OPERATION_RESULT_MISSING)
    return payload


def _parse_model(model_type: type[TModel], payload: Any) -> TModel:
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise AppError(
            message_supabase_payload_schema_mismatch(model_type.__name__),
            code=ErrorCode.INTERNAL_UNEXPECTED,
        ) from exc


def _json_object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _datetime_field(row: Mapping[str, Any], key: str) -> datetime:
    return _optional_datetime_field(row, key) or datetime.now(UTC)


def _optional_datetime_field(row: Mapping[str, Any], key: str) -> datetime | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _queue_error_detail(row: Mapping[str, Any]) -> str:
    payload = row.get("error_payload")
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message")
        if detail:
            return str(detail)
    return MESSAGE_OPERATION_REQUEST_FAILED


def _supabase_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return message_supabase_data_api_http_error(response.status_code)
    if isinstance(payload, dict):
        for key in ("message", "msg", "hint", "details"):
            value = payload.get(key)
            if value:
                return str(value)
    return message_supabase_data_api_http_error(response.status_code)
