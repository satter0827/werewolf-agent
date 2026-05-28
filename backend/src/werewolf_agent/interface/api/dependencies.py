"""FastAPI dependency helpers."""

from __future__ import annotations

from typing import cast

from fastapi import Request

from werewolf_agent.interface.application.games import GameApplication


def game_application(request: Request) -> GameApplication:
    """Return the game application adapter from FastAPI app state."""
    return cast(GameApplication, request.app.state.game_application)
