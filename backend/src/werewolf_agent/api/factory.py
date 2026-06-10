"""Factory for the single public game API surface."""

from __future__ import annotations

from werewolf_agent.api.local_demo import InMemoryGameRepository, LocalDemoGameApi
from werewolf_agent.api.ports import GameApi
from werewolf_agent.api.supabase import (
    SupabaseAuthApi,
    SupabaseGameApi,
    SupabaseSessionStore,
)
from werewolf_agent.commons.configuration import AppSettings

_DEMO_REPOSITORY = InMemoryGameRepository()


def build_game_api(settings: AppSettings) -> GameApi:
    """Return Supabase-backed client when logged in, otherwise local demo client."""
    if not settings.supabase_client_configured:
        return LocalDemoGameApi(settings, repository=_DEMO_REPOSITORY)

    store = SupabaseSessionStore()
    session = store.load()
    if session is None:
        return LocalDemoGameApi(settings, repository=_DEMO_REPOSITORY)
    if session.is_expired:
        auth = SupabaseAuthApi(
            settings.supabase_url,
            settings.supabase_publishable_key_value,
            timeout=settings.supabase_auth_timeout_seconds,
        )
        session = auth.refresh(session)
        store.save(session)
    return SupabaseGameApi(settings, session)
