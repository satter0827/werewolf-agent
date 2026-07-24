"""Factory for the public game client."""

from __future__ import annotations

from werewolf_agent.adapters.auth import ensure_session, require_supabase_client_config
from werewolf_agent.adapters.ports import GameClient
from werewolf_agent.adapters.supabase import SupabaseGameClient
from werewolf_agent.configuration import AppSettings


def build_game_client(settings: AppSettings) -> GameClient:
    """Return the Supabase-backed game client."""
    require_supabase_client_config(settings)
    return SupabaseGameClient(settings, ensure_session(settings))
