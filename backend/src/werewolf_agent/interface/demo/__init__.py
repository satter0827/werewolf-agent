"""In-process demo adapters used when no Supabase session is active."""

from werewolf_agent.interface.demo.client import DemoGameClient
from werewolf_agent.interface.demo.repository import InMemoryGameRepository

__all__ = ["DemoGameClient", "InMemoryGameRepository"]
