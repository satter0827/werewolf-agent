"""Supabase adapters for direct UI/CLI access and worker persistence."""

from werewolf_agent.interface.supabase.auth import SupabaseAuthClient
from werewolf_agent.interface.supabase.client import SupabaseGameClient
from werewolf_agent.interface.supabase.session_store import SupabaseSession, SupabaseSessionStore

__all__ = [
    "SupabaseAuthClient",
    "SupabaseGameClient",
    "SupabaseSession",
    "SupabaseSessionStore",
]
