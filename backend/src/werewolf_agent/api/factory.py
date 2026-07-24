"""Factory for the single public game API surface."""

from __future__ import annotations

from werewolf_agent.api.auth import ensure_session, require_supabase_client_config
from werewolf_agent.api.ports import GameApi
from werewolf_agent.api.supabase import SupabaseGameApi
from werewolf_agent.commons.configuration import AppSettings


def build_game_api(settings: AppSettings) -> GameApi:
    """Return the Supabase-backed game client."""
    require_supabase_client_config(settings)
    return SupabaseGameApi(settings, ensure_session(settings))
