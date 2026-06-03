"""Minimal operational FastAPI routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from werewolf_agent.commons.shared.constants import HEALTH_STATUS_OK
from werewolf_agent.interface.runtime import AppSettings
from werewolf_agent.interface.shared.constants import API_PREFIX

router = APIRouter(prefix=API_PREFIX)


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    """Return process health for deployment checks."""
    settings = request.app.state.settings
    assert isinstance(settings, AppSettings)
    return {
        "status": HEALTH_STATUS_OK,
        "service": settings.api_service_name,
        "data": "supabase" if settings.supabase_client_configured else "demo",
    }
