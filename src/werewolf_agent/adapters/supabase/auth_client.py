"""Supabase Auth SDK adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from supabase_auth import AuthResponse, SyncGoTrueClient  # type: ignore[attr-defined]
from supabase_auth.errors import AuthApiError, AuthError, AuthRetryableError

from werewolf_agent.adapters.supabase.messages import (
    MESSAGE_SUPABASE_AUTH_INCOMPLETE_SESSION,
    MESSAGE_SUPABASE_AUTH_UNAVAILABLE,
)
from werewolf_agent.adapters.supabase.session_store import SupabaseSession
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode


class SupabaseAuthClient:
    """Expose only the authentication operations used by local clients."""

    def __init__(
        self,
        supabase_url: str,
        publishable_key: str,
        *,
        timeout: float,
        client: Any | None = None,
    ) -> None:
        """Create a non-persistent SDK client for one Supabase project."""
        base_url = supabase_url.rstrip("/")
        self._client = client or SyncGoTrueClient(
            url=f"{base_url}/auth/v1",
            headers={
                "apikey": publishable_key,
                "Authorization": f"Bearer {publishable_key}",
            },
            auto_refresh_token=False,
            persist_session=False,
            http_client=httpx.Client(timeout=timeout),
        )

    def sign_in_anonymously(self) -> SupabaseSession:
        """Create an anonymous Supabase session."""
        return self._invoke(lambda: self._client.sign_in_anonymously())

    def sign_in_with_password(self, email: str, password: str) -> SupabaseSession:
        """Create a non-anonymous session from user credentials."""
        return self._invoke(
            lambda: self._client.sign_in_with_password({"email": email, "password": password})
        )

    def sign_out(self, session: SupabaseSession) -> None:
        """Invalidate the current server-side Auth session."""
        try:
            self._client.set_session(session.access_token, session.refresh_token)
            self._client.sign_out()
        except AuthApiError as exc:
            raise AppError(
                "認証sessionを終了できませんでした。",
                code=ErrorCode.AUTHENTICATION_REQUIRED,
            ) from exc
        except (AuthRetryableError, AuthError, httpx.HTTPError) as exc:
            raise AppError(
                MESSAGE_SUPABASE_AUTH_UNAVAILABLE,
                code=ErrorCode.API_UNAVAILABLE,
                retryable=True,
            ) from exc

    def refresh(self, session: SupabaseSession) -> SupabaseSession:
        """Refresh an expired access token."""
        return self._invoke(lambda: self._client.refresh_session(session.refresh_token))

    def _invoke(self, operation: Any) -> SupabaseSession:
        try:
            response = operation()
        except AuthApiError as exc:
            raise AppError(
                "認証情報を確認できませんでした。",
                code=ErrorCode.AUTHENTICATION_REQUIRED,
            ) from exc
        except (AuthRetryableError, AuthError, httpx.HTTPError) as exc:
            raise AppError(
                MESSAGE_SUPABASE_AUTH_UNAVAILABLE,
                code=ErrorCode.API_UNAVAILABLE,
                retryable=True,
            ) from exc
        return _session_from_response(response)


def _session_from_response(response: AuthResponse) -> SupabaseSession:
    sdk_session = response.session
    if sdk_session is None or sdk_session.user is None:
        raise AppError(MESSAGE_SUPABASE_AUTH_INCOMPLETE_SESSION)
    access_token = str(sdk_session.access_token).strip()
    refresh_token = str(sdk_session.refresh_token).strip()
    user_id = str(sdk_session.user.id).strip()
    if not access_token or not refresh_token or not user_id:
        raise AppError(MESSAGE_SUPABASE_AUTH_INCOMPLETE_SESSION)
    expires_at = (
        datetime.fromtimestamp(sdk_session.expires_at - 30, UTC)
        if sdk_session.expires_at is not None
        else datetime.now(UTC) + timedelta(seconds=max(sdk_session.expires_in - 30, 0))
    )
    return SupabaseSession(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        user_id=user_id,
        email=sdk_session.user.email or "",
        is_anonymous=sdk_session.user.is_anonymous,
    )
