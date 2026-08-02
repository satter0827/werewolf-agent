"""Authentication helpers shared by external adapters."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Protocol

from werewolf_agent.adapters.messages import MESSAGE_SUPABASE_CLIENT_CONFIG_REQUIRED
from werewolf_agent.adapters.supabase.auth_client import (
    MfaEnrollment,
    MfaFactor,
    SupabaseAuthClient,
)
from werewolf_agent.adapters.supabase.session_store import SupabaseSession as SupabaseSession
from werewolf_agent.adapters.supabase.session_store import (
    SupabaseSessionStore as SupabaseSessionStore,
)
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.settings import AppSettings

_bound_session: ContextVar[SupabaseSession | None] = ContextVar(
    "werewolf_agent_bound_session",
    default=None,
)


class SessionStore(Protocol):
    """Minimal session persistence contract for CLI and server-side UI sessions."""

    def load(self) -> SupabaseSession | None:
        """Return the current session when one has been saved."""
        ...

    def save(self, session: SupabaseSession) -> None:
        """Persist one authenticated or anonymous session."""
        ...

    def clear(self) -> None:
        """Remove the persisted session."""
        ...


def ensure_session(
    settings: AppSettings,
    *,
    store: SessionStore | None = None,
) -> SupabaseSession:
    """Return a fresh Supabase session, creating an anonymous user when absent."""
    require_supabase_client_config(settings)
    auth = _auth_client(settings)
    session_store = store or SupabaseSessionStore(settings.supabase_url)
    session = session_store.load()
    if session is None:
        session = auth.sign_in_anonymously()
        session_store.save(session)
        return session
    if not session.is_expired:
        return session
    try:
        session = auth.refresh(session)
    except AppError:
        session = auth.sign_in_anonymously()
    session_store.save(session)
    return session


def sign_in_with_password(
    settings: AppSettings,
    email: str,
    password: str,
    *,
    store: SessionStore,
) -> SupabaseSession:
    """Authenticate and replace the session held by one interface."""
    require_supabase_client_config(settings)
    session = _auth_client(settings).sign_in_with_password(email.strip(), password)
    store.save(session)
    return session


def list_totp_factors(
    settings: AppSettings,
    *,
    store: SessionStore,
) -> tuple[MfaFactor, ...]:
    """Return verified TOTP factors for the current non-anonymous session."""
    session = _member_session(settings, store=store)
    return _auth_client(settings).list_totp_factors(session)


def enroll_totp(
    settings: AppSettings,
    *,
    friendly_name: str,
    store: SessionStore,
) -> MfaEnrollment:
    """Start TOTP enrollment for the current non-anonymous session."""
    session = _member_session(settings, store=store)
    name = friendly_name.strip()
    if not name:
        raise AppError(
            "多要素認証端末の名前が必要です。",
            code=ErrorCode.CONFIG_INVALID_VALUE,
        )
    return _auth_client(settings).enroll_totp(session, friendly_name=name)


def verify_totp(
    settings: AppSettings,
    factor_id: str,
    code: str,
    *,
    store: SessionStore,
) -> SupabaseSession:
    """Upgrade the current session with one verified TOTP factor."""
    session = _member_session(settings, store=store)
    normalized_factor_id = factor_id.strip()
    normalized_code = code.strip()
    if not normalized_factor_id or len(normalized_code) != 6 or not normalized_code.isdigit():
        raise AppError(
            "6桁の多要素認証コードを入力してください。",
            code=ErrorCode.CONFIG_INVALID_VALUE,
        )
    elevated = _auth_client(settings).verify_totp(
        session,
        factor_id=normalized_factor_id,
        code=normalized_code,
    )
    store.save(elevated)
    return elevated


def sign_out(
    settings: AppSettings,
    *,
    store: SessionStore,
) -> SupabaseSession:
    """End the current session and return a fresh guest session."""
    require_supabase_client_config(settings)
    auth = _auth_client(settings)
    current = store.load()
    if current is not None:
        auth.sign_out(current)
    store.clear()
    guest = auth.sign_in_anonymously()
    store.save(guest)
    return guest


@contextmanager
def bind_session(session: SupabaseSession) -> Iterator[None]:
    """Bind one interface session for nested HTTP client construction."""
    token = _bound_session.set(session)
    try:
        yield
    finally:
        _bound_session.reset(token)


def current_bound_session() -> SupabaseSession | None:
    """Return the session scoped to the current interface request."""
    return _bound_session.get()


def require_supabase_client_config(settings: AppSettings) -> None:
    """Raise a clear error when CLI/UI Supabase settings are absent."""
    if settings.supabase_client_configured:
        return
    raise AppError(
        MESSAGE_SUPABASE_CLIENT_CONFIG_REQUIRED,
        code=ErrorCode.CONFIG_INVALID_VALUE,
    )


def _member_session(settings: AppSettings, *, store: SessionStore) -> SupabaseSession:
    session = ensure_session(settings, store=store)
    if session.is_anonymous:
        raise AppError(
            "多要素認証にはログインが必要です。",
            code=ErrorCode.AUTHENTICATION_REQUIRED,
        )
    return session


def _auth_client(settings: AppSettings) -> SupabaseAuthClient:
    return SupabaseAuthClient(
        settings.supabase_url,
        settings.supabase_publishable_key_value,
        timeout=settings.supabase_auth_timeout_seconds,
    )
