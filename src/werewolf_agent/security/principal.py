"""Verified request principal."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from werewolf_agent.settings import AppSettings


class AuthenticationError(Exception):
    """Raised when a bearer token cannot be verified."""


class AdminSessionUnavailable(Exception):
    """Raised when current administrator session state cannot be verified."""


class AdminSessionVerifier(Protocol):
    """Verify current server-side state for a sensitive administrator session."""

    def verify(
        self,
        token: str,
        *,
        expected_user_id: str,
        expected_session_id: str,
    ) -> bool:
        """Return whether Auth still recognizes the administrator session."""


@dataclass(frozen=True)
class Principal:
    """Identity derived exclusively from a verified access token."""

    user_id: str
    is_anonymous: bool
    is_admin: bool

    @property
    def llm_mode(self) -> Literal["fake", "paid"]:
        """Return the server-selected LLM mode for newly created games."""
        return "fake" if self.is_anonymous else "paid"


class Authenticator(Protocol):
    """Access-token verification port used by the HTTP boundary."""

    def authenticate(self, token: str) -> Principal:
        """Verify a token and return its allowlisted identity."""


class SupabaseJwtAuthenticator:
    """Verify Supabase JWT signature and registered claims through JWKS."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        admin_session_verifier: AdminSessionVerifier | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Create a verifier with issuer, audience, and rotating JWKS settings."""
        self._issuer = settings.resolved_supabase_jwt_issuer
        self._audience = settings.supabase_jwt_audience
        self._jwks_url = settings.resolved_supabase_jwks_url
        self._admin_max_token_age_seconds = settings.api_admin_max_token_age_seconds
        self._admin_session_verifier = admin_session_verifier
        self._clock = clock
        self._client: Any | None = None

    def authenticate(self, token: str) -> Principal:
        """Verify signature, issuer, audience, expiry, and identity claims."""
        try:
            import jwt

            client = self._client
            if client is None:
                client = jwt.PyJWKClient(self._jwks_url, cache_keys=True)
                self._client = client
            key = client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256", "ES256"],
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": ["sub", "exp", "iat", "aud", "iss"],
                    "verify_exp": True,
                },
            )
        except Exception as exc:
            raise AuthenticationError("認証情報を確認できませんでした。") from exc

        user_id = str(claims.get("sub") or "").strip()
        if not user_id:
            raise AuthenticationError("認証情報に利用者IDがありません。")
        app_metadata = claims.get("app_metadata")
        metadata = app_metadata if isinstance(app_metadata, dict) else {}
        is_admin = self._is_current_admin(
            token,
            user_id=user_id,
            claims=claims,
            metadata=metadata,
        )
        return Principal(
            user_id=user_id,
            is_anonymous=bool(claims.get("is_anonymous", False)),
            is_admin=is_admin,
        )

    def _is_current_admin(
        self,
        token: str,
        *,
        user_id: str,
        claims: dict[str, Any],
        metadata: dict[str, Any],
    ) -> bool:
        """Require signed role, MFA, fresh issuance, and a live Auth session."""
        if bool(claims.get("is_anonymous", False)):
            return False
        if str(metadata.get("role") or "") != "admin":
            return False
        if claims.get("aal") != "aal2":
            return False
        session_id = str(claims.get("session_id") or "").strip()
        if not session_id:
            return False
        issued_at = claims.get("iat")
        if isinstance(issued_at, bool) or not isinstance(issued_at, (int, float)):
            return False
        token_age = self._clock() - float(issued_at)
        if token_age < 0 or token_age > self._admin_max_token_age_seconds:
            return False
        verifier = self._admin_session_verifier
        if verifier is None:
            return False
        try:
            return verifier.verify(
                token,
                expected_user_id=user_id,
                expected_session_id=session_id,
            )
        except AdminSessionUnavailable:
            return False


__all__ = [
    "AdminSessionUnavailable",
    "AdminSessionVerifier",
    "AuthenticationError",
    "Authenticator",
    "Principal",
    "SupabaseJwtAuthenticator",
]
