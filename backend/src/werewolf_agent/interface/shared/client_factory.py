"""Factory for the single public game client surface."""

from __future__ import annotations

from werewolf_agent.interface.demo import DemoGameClient, InMemoryGameRepository
from werewolf_agent.interface.runtime import AppSettings
from werewolf_agent.interface.shared.game_client import GameClient
from werewolf_agent.interface.supabase import (
    SupabaseAuthClient,
    SupabaseGameClient,
    SupabaseSessionStore,
)

_DEMO_REPOSITORY = InMemoryGameRepository()


def build_game_client(settings: AppSettings) -> GameClient:
    """Return Supabase-backed client when logged in, otherwise local demo client."""
    if not settings.supabase_client_configured:
        return DemoGameClient(settings, repository=_DEMO_REPOSITORY)

    store = SupabaseSessionStore()
    session = store.load()
    if session is None:
        return DemoGameClient(settings, repository=_DEMO_REPOSITORY)
    if session.is_expired:
        auth = SupabaseAuthClient(
            settings.supabase_url,
            settings.supabase_publishable_key_value,
            timeout=settings.supabase_auth_timeout_seconds,
        )
        session = auth.refresh(session)
        store.save(session)
    return SupabaseGameClient(settings, session)
