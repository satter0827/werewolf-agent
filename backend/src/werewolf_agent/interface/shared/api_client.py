"""HTTP client for public Werewolf Agent API entry points."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from werewolf_agent.commons.shared.constants import (
    DURATION_MILLISECONDS_DECIMAL_PLACES,
    EVENT_OUTCOME_FAILURE,
    EVENT_OUTCOME_SUCCESS,
    HTTP_FAILURE_STATUS_MIN,
    HTTP_SERVER_ERROR_STATUS_MIN,
    MIN_PAGE_OFFSET,
    SECONDS_TO_MILLISECONDS,
)
from werewolf_agent.commons.shared.messages import (
    LOG_SHARED_API_REQUEST_COMPLETED,
    MESSAGE_API_RESPONSE_NOT_JSON,
    MESSAGE_API_RESPONSE_NOT_OBJECT,
    MESSAGE_API_RESPONSE_SCHEMA_MISMATCH,
    message_api_http_error,
    message_api_unavailable,
    message_problem_detail,
)
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    AdvanceGameResponse,
    CreateGameRequest,
    GameListResponse,
    GameResponse,
    GameRevealResponse,
    GameSetupOptionsResponse,
    GameTimelineResponse,
    PlayerActionRequest,
    PlayerActionResponse,
    PlayerObservationResponse,
    ProblemDetails,
)
from werewolf_agent.interface.runtime import get_observation_context
from werewolf_agent.interface.shared.constants import (
    AUTHORIZATION_HEADER,
    BEARER_AUTH_SCHEME,
    TRACE_ID_HEADER,
)
from werewolf_agent.interface.shared.log_sanitization import safe_http_log_path

TModel = TypeVar("TModel", bound=BaseModel)
logger = logging.getLogger(__name__)


class GameApiClient(Protocol):
    """Client operations used by interface entry points without internal services."""

    def health(self) -> dict[str, str]:
        """Fetch API health through the public API."""

    def get_setup_options(self) -> GameSetupOptionsResponse:
        """Fetch game setup options through the public API."""

    def create_game(self, request: CreateGameRequest) -> GameResponse:
        """Create one game through the public API."""

    def get_game(self, game_id: str) -> GameResponse:
        """Fetch one game through the public API."""

    def get_game_reveal(self, game_id: str) -> GameRevealResponse:
        """Fetch full observer-only game information through the reveal API."""

    def list_games(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> GameListResponse:
        """Fetch public game summaries through the public API."""

    def advance_game(self, game_id: str) -> AdvanceGameResponse:
        """Advance one game through the public API."""

    def get_timeline(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int | None = None,
    ) -> GameTimelineResponse:
        """Fetch public game timeline items through the public API."""

    def get_private_observation(
        self,
        game_id: str,
        player_id: str,
        *,
        manual_token: str,
    ) -> PlayerObservationResponse:
        """Fetch one player's private observation."""

    def submit_player_action(
        self,
        game_id: str,
        player_id: str,
        request: PlayerActionRequest,
        *,
        manual_token: str,
    ) -> PlayerActionResponse:
        """Submit one manual player action."""


class HttpGameApiClient:
    """Small httpx-backed client for the public API."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Create a client bound to one API base URL."""
        self.base_url = base_url.rstrip("/") + "/"
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
        )

    def health(self) -> dict[str, str]:
        """Fetch API health through the public API."""
        payload = self._request_json("GET", "health")
        return {key: str(value) for key, value in payload.items()}

    def get_setup_options(self) -> GameSetupOptionsResponse:
        """Fetch game setup options through the public API."""
        payload = self._request_json("GET", "setup-options")
        return self._parse_model(GameSetupOptionsResponse, payload)

    def create_game(self, request: CreateGameRequest) -> GameResponse:
        """Create one game through the public API."""
        payload = self._request_json(
            "POST",
            "games",
            body=request.model_dump(mode="json", exclude_none=True, exclude_defaults=True),
        )
        return self._parse_model(GameResponse, payload)

    def get_game(self, game_id: str) -> GameResponse:
        """Fetch one game through the public API."""
        payload = self._request_json("GET", f"games/{game_id}")
        return self._parse_model(GameResponse, payload)

    def get_game_reveal(self, game_id: str) -> GameRevealResponse:
        """Fetch full observer-only game information through the reveal API."""
        payload = self._request_json("GET", f"games/{game_id}/reveal")
        return self._parse_model(GameRevealResponse, payload)

    def list_games(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> GameListResponse:
        """Fetch public game summaries through the public API."""
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset != MIN_PAGE_OFFSET:
            params["offset"] = offset
        if status is not None:
            params["status"] = status
        payload = self._request_json("GET", "games", params=params)
        return self._parse_model(GameListResponse, payload)

    def advance_game(self, game_id: str) -> AdvanceGameResponse:
        """Advance one game through the public API."""
        payload = self._request_json("POST", f"games/{game_id}/advance")
        return self._parse_model(AdvanceGameResponse, payload)

    def get_timeline(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int | None = None,
    ) -> GameTimelineResponse:
        """Fetch public game timeline items through the public API."""
        params: dict[str, Any] = {}
        if after != MIN_PAGE_OFFSET:
            params["after"] = after
        if limit is not None:
            params["limit"] = limit
        payload = self._request_json(
            "GET",
            f"games/{game_id}/timeline",
            params=params,
        )
        return self._parse_model(GameTimelineResponse, payload)

    def get_private_observation(
        self,
        game_id: str,
        player_id: str,
        *,
        manual_token: str,
    ) -> PlayerObservationResponse:
        """Fetch one player's private observation."""
        payload = self._request_json(
            "GET",
            f"games/{game_id}/players/{player_id}/observation",
            headers=_authorization_header(manual_token),
        )
        return self._parse_model(PlayerObservationResponse, payload)

    def submit_player_action(
        self,
        game_id: str,
        player_id: str,
        request: PlayerActionRequest,
        *,
        manual_token: str,
    ) -> PlayerActionResponse:
        """Submit one manual player action."""
        payload = self._request_json(
            "POST",
            f"games/{game_id}/players/{player_id}/actions",
            body=request.model_dump(mode="json", exclude_none=True),
            headers=_authorization_header(manual_token),
        )
        return self._parse_model(PlayerActionResponse, payload)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        request_headers = _request_headers(headers)
        try:
            response = self._client.request(
                method,
                path,
                json=body,
                params=params,
                headers=request_headers,
            )
            logger.debug(
                LOG_SHARED_API_REQUEST_COMPLETED,
                extra={
                    "event_action": LOG_SHARED_API_REQUEST_COMPLETED,
                    "event_outcome": (
                        EVENT_OUTCOME_SUCCESS
                        if response.status_code < HTTP_FAILURE_STATUS_MIN
                        else EVENT_OUTCOME_FAILURE
                    ),
                    "method": method,
                    "path": safe_http_log_path(path),
                    "http_status": response.status_code,
                    "duration_ms": round(
                        (time.perf_counter() - started) * SECONDS_TO_MILLISECONDS,
                        DURATION_MILLISECONDS_DECIMAL_PLACES,
                    ),
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _api_error_from_response(exc.response) from exc
        except httpx.HTTPError as exc:
            raise AppError(
                message_api_unavailable(exc),
                code=ErrorCode.API_UNAVAILABLE,
            ) from exc

        if not response.content:
            return {}

        try:
            payload = response.json()
        except ValueError as exc:
            raise AppError(
                MESSAGE_API_RESPONSE_NOT_JSON,
                code=ErrorCode.INTERNAL_UNEXPECTED,
            ) from exc

        if not isinstance(payload, dict):
            raise AppError(
                MESSAGE_API_RESPONSE_NOT_OBJECT,
                code=ErrorCode.INTERNAL_UNEXPECTED,
            )
        return payload

    def _parse_model(self, model_type: type[TModel], payload: dict[str, Any]) -> TModel:
        try:
            return model_type.model_validate(payload)
        except ValidationError as exc:
            raise AppError(
                MESSAGE_API_RESPONSE_SCHEMA_MISMATCH,
                code=ErrorCode.INTERNAL_UNEXPECTED,
                context={"schema": model_type.__name__},
            ) from exc


def build_game_api_client(
    api_url: str,
    *,
    timeout: float,
    transport: httpx.BaseTransport | None = None,
) -> GameApiClient:
    """Build a public API client for interface entry points."""
    return HttpGameApiClient(api_url, timeout=timeout, transport=transport)


def _api_error_from_response(response: httpx.Response) -> AppError:
    if response.content:
        try:
            problem = ProblemDetails.model_validate(response.json())
        except (ValueError, ValidationError):
            problem = None
        if problem is not None:
            return _app_error_from_problem(problem)

    return AppError(
        message_api_http_error(response.status_code),
        code=ErrorCode.INTERNAL_UNEXPECTED,
        context={"http_status": response.status_code},
    )


def _app_error_from_problem(problem: ProblemDetails) -> AppError:
    try:
        code = ErrorCode(problem.code)
    except ValueError:
        code = ErrorCode.INTERNAL_UNEXPECTED

    return AppError(
        message_problem_detail(problem.code, problem.detail),
        code=code,
        context={"http_status": problem.status, "problem_type": problem.type},
        retryable=problem.status >= HTTP_SERVER_ERROR_STATUS_MIN,
    )


def _authorization_header(manual_token: str) -> dict[str, str]:
    return {AUTHORIZATION_HEADER: f"{BEARER_AUTH_SCHEME} {manual_token}"}


def _request_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    request_headers = dict(headers or {})
    trace_id = get_observation_context().get("trace_id")
    if trace_id and TRACE_ID_HEADER not in request_headers:
        request_headers[TRACE_ID_HEADER] = trace_id
    return request_headers
