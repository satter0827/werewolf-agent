"""Authentication helpers shared by external adapters."""

from __future__ import annotations

from werewolf_agent.adapters.supabase import (
    SupabaseAuthClient,
    SupabaseSession,
    SupabaseSessionStore,
)
from werewolf_agent.configuration import AppSettings
from werewolf_agent.configuration.messages import MESSAGE_SUPABASE_CLIENT_CONFIG_REQUIRED
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode


def ensure_session(
    settings: AppSettings,
    *,
    store: SupabaseSessionStore | None = None,
) -> SupabaseSession:
    """Return a fresh Supabase session, creating an anonymous user when absent."""
    require_supabase_client_config(settings)
    auth = _auth_client(settings)
    session_store = store or SupabaseSessionStore()
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


def require_supabase_client_config(settings: AppSettings) -> None:
    """Raise a clear error when CLI/UI Supabase settings are absent."""
    if settings.supabase_client_configured:
        return
    raise AppError(
        MESSAGE_SUPABASE_CLIENT_CONFIG_REQUIRED,
        code=ErrorCode.CONFIG_INVALID_VALUE,
    )


def _auth_client(settings: AppSettings) -> SupabaseAuthClient:
    return SupabaseAuthClient(
        settings.supabase_url,
        settings.supabase_publishable_key_value,
        timeout=settings.supabase_auth_timeout_seconds,
    )
