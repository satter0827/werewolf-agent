"""Verified request principal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from werewolf_agent.settings import AppSettings


class AuthenticationError(Exception):
    """Raised when a bearer token cannot be verified."""


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

    def __init__(self, settings: AppSettings) -> None:
        """Create a verifier with issuer, audience, and rotating JWKS settings."""
        self._issuer = settings.resolved_supabase_jwt_issuer
        self._audience = settings.supabase_jwt_audience
        self._jwks_url = settings.resolved_supabase_jwks_url
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
        role = str(metadata.get("role") or claims.get("role") or "")
        return Principal(
            user_id=user_id,
            is_anonymous=bool(claims.get("is_anonymous", False)),
            is_admin=role in {"admin", "service_role"},
        )


__all__ = [
    "AuthenticationError",
    "Authenticator",
    "Principal",
    "SupabaseJwtAuthenticator",
]
