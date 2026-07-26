"""Factories for capability-scoped HTTP clients."""

from __future__ import annotations

from werewolf_agent.adapters.auth import (
    current_bound_session,
    ensure_session,
    require_supabase_client_config,
)
from werewolf_agent.adapters.http import HttpAdminClient, HttpGameClient, HttpPublicClient
from werewolf_agent.adapters.ports import AdminClient, GameClient, PublicClient
from werewolf_agent.settings import AppSettings


def build_public_client(settings: AppSettings) -> PublicClient:
    """Return the unauthenticated runtime client."""
    return HttpPublicClient(settings)


def build_game_client(settings: AppSettings) -> GameClient:
    """Return the authenticated game client."""
    require_supabase_client_config(settings)
    return HttpGameClient(settings, current_bound_session() or ensure_session(settings))


def build_admin_client(settings: AppSettings) -> AdminClient:
    """Return the authenticated administrative client."""
    require_supabase_client_config(settings)
    return HttpAdminClient(settings, current_bound_session() or ensure_session(settings))


__all__ = ["build_admin_client", "build_game_client", "build_public_client"]
