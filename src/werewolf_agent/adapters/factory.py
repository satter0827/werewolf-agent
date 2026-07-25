"""Factory for the public game client."""

from __future__ import annotations

from werewolf_agent.adapters.auth import (
    current_bound_session,
    ensure_session,
    require_supabase_client_config,
)
from werewolf_agent.adapters.http import HttpGameClient
from werewolf_agent.adapters.ports import GameClient
from werewolf_agent.configuration import AppSettings


def build_game_client(settings: AppSettings) -> GameClient:
    """Return the shared HTTP API client used by CLI and Streamlit."""
    require_supabase_client_config(settings)
    return HttpGameClient(settings, current_bound_session() or ensure_session(settings))
