"""FastAPI dependency helpers."""

from __future__ import annotations

from typing import cast

from fastapi import Request

from werewolf_agent.commons.configuration import AppSettings
from werewolf_agent.interface.application.database import SessionFactory


def app_settings(request: Request) -> AppSettings:
    """Return process settings from FastAPI app state."""
    return cast(AppSettings, request.app.state.settings)


def game_session_factory(request: Request) -> SessionFactory:
    """Return the configured session factory from FastAPI app state."""
    return cast(SessionFactory, request.app.state.session_factory)
