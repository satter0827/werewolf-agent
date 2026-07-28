"""Shared HTTP transport for typed API clients."""

from __future__ import annotations

from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from werewolf_agent.adapters.supabase.session_store import SupabaseSession
from werewolf_agent.contracts import AppError, ErrorCode
from werewolf_agent.contracts.schemas import ProblemDetails
from werewolf_agent.settings import AppSettings

TModel = TypeVar("TModel", bound=BaseModel)


class HttpApiClient:
    """Validate typed responses and normalize transport failures."""

    def __init__(
        self,
        settings: AppSettings,
        session: SupabaseSession | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Create a typed HTTP transport with an optional bearer session."""
        headers = (
            {"Authorization": f"Bearer {session.access_token}"} if session is not None else None
        )
        self._client = httpx.Client(
            base_url=settings.api_base_url.rstrip("/"),
            timeout=settings.api_timeout_seconds,
            transport=transport,
            headers=headers,
        )

    def model(
        self,
        model_type: type[TModel],
        method: str,
        path: str,
        **kwargs: Any,
    ) -> TModel:
        """Return one schema-validated response."""
        try:
            response = self._client.request(method, path, **kwargs)
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

    def json(self, method: str, path: str, **kwargs: Any) -> Any:
        """Return one successful JSON response for collection contracts."""
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise AppError(
                "APIへ接続できませんでした。",
                code=ErrorCode.API_UNAVAILABLE,
                retryable=True,
            ) from exc
        if response.is_error:
            _raise_problem(response)
        try:
            return response.json()
        except ValueError as exc:
            raise AppError(
                "API応答の形式を確認できませんでした。",
                code=ErrorCode.INTERNAL_UNEXPECTED,
            ) from exc


def parse_model(model_type: type[TModel], payload: Any) -> TModel:
    """Validate an embedded response payload."""
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
    raise AppError(problem.detail, code=code, retryable=problem.retryable)


__all__ = ["HttpApiClient", "parse_model"]
