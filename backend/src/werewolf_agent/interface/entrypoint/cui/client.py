"""HTTP client for the public Werewolf Agent API contract."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from werewolf_agent.commons.shared.messages import (
    LOG_CLI_API_REQUEST_COMPLETED,
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
    CreateGameRequest,
    GameEventsResponse,
    GameResponse,
    GameRunsResponse,
    GameTurnsResponse,
    PrivateObservationResponse,
    ProblemDetails,
    RulesetResponse,
    StepGameResponse,
    SubmitPlayerActionRequest,
    SubmitPlayerActionResponse,
)

TModel = TypeVar("TModel", bound=BaseModel)
logger = logging.getLogger(__name__)


class GameApiClient(Protocol):
    """Client operations used by the CUI without touching internal services."""

    def health(self) -> dict[str, str]:
        """Fetch API health through the public API."""

    def get_ruleset(self) -> RulesetResponse:
        """Fetch the default ruleset through the public API."""

    def create_game(self, request: CreateGameRequest) -> GameResponse:
        """Create one game through the public API."""

    def get_game(self, game_id: str) -> GameResponse:
        """Fetch one game through the public API."""

    def list_games(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> GameRunsResponse:
        """Fetch public game run summaries through the public API."""

    def step_game(self, game_id: str) -> StepGameResponse:
        """Advance one game through the public API."""

    def list_events(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> GameEventsResponse:
        """Fetch public game events through the public API."""

    def list_turns(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> GameTurnsResponse:
        """Fetch public turn history through the public API."""

    def get_private_observation(
        self,
        game_id: str,
        player_id: str,
        *,
        control_token: str,
    ) -> PrivateObservationResponse:
        """Fetch one player's private observation."""

    def submit_player_action(
        self,
        game_id: str,
        player_id: str,
        request: SubmitPlayerActionRequest,
        *,
        control_token: str,
    ) -> SubmitPlayerActionResponse:
        """Submit one manual player action."""


class HttpGameApiClient:
    """Small httpx-backed client for the public API."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
        )

    def health(self) -> dict[str, str]:
        payload = self._request_json("GET", "health")
        return {key: str(value) for key, value in payload.items()}

    def get_ruleset(self) -> RulesetResponse:
        payload = self._request_json("GET", "rulesets/default")
        return self._parse_model(RulesetResponse, payload)

    def create_game(self, request: CreateGameRequest) -> GameResponse:
        payload = self._request_json(
            "POST",
            "games",
            body=request.model_dump(mode="json", exclude_none=True, exclude_defaults=True),
        )
        return self._parse_model(GameResponse, payload)

    def get_game(self, game_id: str) -> GameResponse:
        payload = self._request_json("GET", f"games/{game_id}")
        return self._parse_model(GameResponse, payload)

    def list_games(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> GameRunsResponse:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        payload = self._request_json("GET", "games", params=params)
        return self._parse_model(GameRunsResponse, payload)

    def step_game(self, game_id: str) -> StepGameResponse:
        payload = self._request_json("POST", f"games/{game_id}/steps")
        return self._parse_model(StepGameResponse, payload)

    def list_events(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> GameEventsResponse:
        payload = self._request_json(
            "GET",
            f"games/{game_id}/events",
            params={"after": after, "limit": limit},
        )
        return self._parse_model(GameEventsResponse, payload)

    def list_turns(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> GameTurnsResponse:
        payload = self._request_json(
            "GET",
            f"games/{game_id}/turns",
            params={"after": after, "limit": limit},
        )
        return self._parse_model(GameTurnsResponse, payload)

    def get_private_observation(
        self,
        game_id: str,
        player_id: str,
        *,
        control_token: str,
    ) -> PrivateObservationResponse:
        payload = self._request_json(
            "GET",
            f"games/{game_id}/players/{player_id}/observation",
            headers=_authorization_header(control_token),
        )
        return self._parse_model(PrivateObservationResponse, payload)

    def submit_player_action(
        self,
        game_id: str,
        player_id: str,
        request: SubmitPlayerActionRequest,
        *,
        control_token: str,
    ) -> SubmitPlayerActionResponse:
        payload = self._request_json(
            "POST",
            f"games/{game_id}/players/{player_id}/actions",
            body=request.model_dump(mode="json", exclude_none=True),
            headers=_authorization_header(control_token),
        )
        return self._parse_model(SubmitPlayerActionResponse, payload)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._client.request(
                method,
                path,
                json=body,
                params=params,
                headers=headers,
            )
            logger.debug(
                LOG_CLI_API_REQUEST_COMPLETED,
                extra={"method": method, "path": path, "http_status": response.status_code},
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
        retryable=problem.status >= 500,
    )


def _authorization_header(control_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {control_token}"}
