"""Supabase Auth REST client."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from werewolf_agent.adapters.supabase.session_store import SupabaseSession
from werewolf_agent.configuration.messages import (
    MESSAGE_SUPABASE_AUTH_INCOMPLETE_SESSION,
    MESSAGE_SUPABASE_AUTH_INVALID_RESPONSE,
    MESSAGE_SUPABASE_AUTH_UNAVAILABLE,
    message_supabase_auth_http_error,
)
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode


class SupabaseAuthClient:
    """Small GoTrue client for anonymous sessions."""

    def __init__(
        self,
        supabase_url: str,
        publishable_key: str,
        *,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Create an auth client bound to one Supabase project."""
        self._base_url = supabase_url.rstrip("/")
        self._publishable_key = publishable_key
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def sign_in_anonymously(self) -> SupabaseSession:
        """Create an anonymous Supabase session."""
        payload = self._request_json(
            "POST",
            "/auth/v1/signup",
            json_body={},
        )
        return _session_from_auth_payload(payload)

    def refresh(self, session: SupabaseSession) -> SupabaseSession:
        """Refresh an expired access token."""
        payload = self._request_json(
            "POST",
            "/auth/v1/token?grant_type=refresh_token",
            json_body={"refresh_token": session.refresh_token},
        )
        return _session_from_auth_payload(payload)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, object],
        bearer_token: str | None = None,
    ) -> dict[str, Any]:
        headers = {
            "apikey": self._publishable_key,
            "Content-Type": "application/json",
        }
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        try:
            response = self._client.request(
                method,
                f"{self._base_url}{path}",
                json=json_body,
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json() if response.content else {}
        except httpx.HTTPStatusError as exc:
            raise AppError(
                _supabase_error_detail(exc.response),
                code=ErrorCode.AUTHENTICATION_REQUIRED,
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise AppError(
                MESSAGE_SUPABASE_AUTH_UNAVAILABLE,
                code=ErrorCode.API_UNAVAILABLE,
                retryable=True,
            ) from exc
        if not isinstance(payload, dict):
            raise AppError(MESSAGE_SUPABASE_AUTH_INVALID_RESPONSE)
        return payload


def _session_from_auth_payload(payload: dict[str, Any]) -> SupabaseSession:
    access_token = str(payload.get("access_token") or "")
    refresh_token = str(payload.get("refresh_token") or "")
    expires_in = int(payload.get("expires_in") or 3600)
    user = payload.get("user")
    if not access_token or not refresh_token or not isinstance(user, dict):
        raise AppError(MESSAGE_SUPABASE_AUTH_INCOMPLETE_SESSION)
    expires_at = datetime.now(UTC) + timedelta(seconds=max(expires_in - 30, 0))
    return SupabaseSession(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        user_id=str(user.get("id") or ""),
        email=str(user.get("email") or ""),
        is_anonymous=bool(user.get("is_anonymous", False)),
    )


def _supabase_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return message_supabase_auth_http_error(response.status_code)
    if isinstance(payload, dict):
        for key in ("msg", "message", "error_description", "error"):
            value = payload.get(key)
            if value:
                return str(value)
    return message_supabase_auth_http_error(response.status_code)
