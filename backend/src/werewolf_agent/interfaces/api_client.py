"""HTTP client for the public Werewolf Agent API contract."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol, TypeVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from pydantic import BaseModel, ValidationError

from werewolf_agent.commons import AppError, ErrorCode
from werewolf_agent.commons.schemas import ProblemDetails
from werewolf_agent.interfaces.api.schemas import (
    CreateGameRequest,
    GameEventsResponse,
    GameResponse,
    StepGameResponse,
)

TModel = TypeVar("TModel", bound=BaseModel)


class GameApiClient(Protocol):
    """Client operations used by the CLI without touching internal services."""

    def create_game(self, request: CreateGameRequest) -> GameResponse:
        """Create one game through the public API."""

    def get_game(self, game_id: str) -> GameResponse:
        """Fetch one game through the public API."""

    def step_game(self, game_id: str) -> StepGameResponse:
        """Advance one game through the public API."""

    def list_events(self, game_id: str, *, after: int = 0) -> GameEventsResponse:
        """Fetch public game events through the public API."""


class HttpGameApiClient:
    """Small urllib-backed client for the public API."""

    def __init__(self, base_url: str, *, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout

    def create_game(self, request: CreateGameRequest) -> GameResponse:
        payload = self._request_json(
            "POST",
            "games/",
            body=request.model_dump(mode="json", exclude_none=True, exclude_defaults=True),
        )
        return self._parse_model(GameResponse, payload)

    def get_game(self, game_id: str) -> GameResponse:
        payload = self._request_json("GET", f"games/{game_id}/")
        return self._parse_model(GameResponse, payload)

    def step_game(self, game_id: str) -> StepGameResponse:
        payload = self._request_json("POST", f"games/{game_id}/steps/")
        return self._parse_model(StepGameResponse, payload)

    def list_events(self, game_id: str, *, after: int = 0) -> GameEventsResponse:
        query = urlencode({"after": after})
        payload = self._request_json("GET", f"games/{game_id}/events/?{query}")
        return self._parse_model(GameEventsResponse, payload)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_body = None
        headers = {"Accept": "application/json"}
        if body is not None:
            request_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(
            urljoin(self.base_url, path),
            data=request_body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise _api_error_from_http_error(exc) from exc
        except (TimeoutError, URLError) as exc:
            raise AppError(
                f"api.unavailable: Could not connect to API ({exc}).",
                code=ErrorCode.API_UNAVAILABLE,
            ) from exc

        if not response_body:
            return {}

        try:
            payload = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise AppError(
                "api.invalid_response: API response was not valid JSON.",
                code=ErrorCode.INTERNAL_UNEXPECTED,
            ) from exc

        if not isinstance(payload, dict):
            raise AppError(
                "api.invalid_response: API response was not a JSON object.",
                code=ErrorCode.INTERNAL_UNEXPECTED,
            )
        return payload

    def _parse_model(self, model_type: type[TModel], payload: dict[str, Any]) -> TModel:
        try:
            return model_type.model_validate(payload)
        except ValidationError as exc:
            raise AppError(
                "api.invalid_response: API response did not match the public schema.",
                code=ErrorCode.INTERNAL_UNEXPECTED,
                context={"schema": model_type.__name__},
            ) from exc


def _api_error_from_http_error(error: HTTPError) -> AppError:
    body = error.read().decode("utf-8", errors="replace")
    if body:
        try:
            problem = ProblemDetails.model_validate_json(body)
        except ValidationError:
            problem = None
        if problem is not None:
            return _app_error_from_problem(problem)

    return AppError(
        f"api.http_error: API request failed with HTTP {error.code}.",
        code=ErrorCode.INTERNAL_UNEXPECTED,
        context={"http_status": error.code},
    )


def _app_error_from_problem(problem: ProblemDetails) -> AppError:
    try:
        code = ErrorCode(problem.code)
    except ValueError:
        code = ErrorCode.INTERNAL_UNEXPECTED

    return AppError(
        f"{problem.code}: {problem.detail}",
        code=code,
        context={"http_status": problem.status, "problem_type": problem.type},
        retryable=problem.status >= 500,
    )
