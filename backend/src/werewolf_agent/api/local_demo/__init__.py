"""Process-local demo API implementation."""

from werewolf_agent.api.local_demo.game_api import LocalDemoGameApi
from werewolf_agent.api.local_demo.repository import InMemoryGameRepository

__all__ = ["InMemoryGameRepository", "LocalDemoGameApi"]
