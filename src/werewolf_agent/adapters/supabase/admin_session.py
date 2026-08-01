"""Live Supabase Auth verification for administrator sessions."""

from __future__ import annotations

from typing import Any

import httpx

from werewolf_agent.security.principal import AdminSessionUnavailable
from werewolf_agent.settings import AppSettings


class SupabaseAdminSessionVerifier:
    """Confirm sensitive authorization against current Supabase Auth state."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Create a reusable Auth client without persisting user credentials."""
        self._publishable_key = settings.supabase_publishable_key_value
        self._client = httpx.Client(
            base_url=f"{settings.supabase_url.rstrip('/')}/auth/v1",
            timeout=settings.supabase_auth_timeout_seconds,
            transport=transport,
        )

    def verify(self, token: str, *, expected_user_id: str) -> bool:
        """Require a live session, matching user, and current administrator role."""
        try:
            response = self._client.get(
                "/user",
                headers={
                    "apikey": self._publishable_key,
                    "Authorization": f"Bearer {token}",
                },
            )
        except httpx.HTTPError as exc:
            raise AdminSessionUnavailable from exc
        if response.status_code in {401, 403}:
            return False
        if not response.is_success:
            raise AdminSessionUnavailable
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise AdminSessionUnavailable from exc
        if not isinstance(payload, dict):
            return False
        app_metadata = payload.get("app_metadata")
        metadata = app_metadata if isinstance(app_metadata, dict) else {}
        return (
            str(payload.get("id") or "").strip() == expected_user_id
            and str(metadata.get("role") or "") == "admin"
        )

    def close(self) -> None:
        """Release the reusable HTTP connection pool."""
        self._client.close()


__all__ = ["SupabaseAdminSessionVerifier"]
