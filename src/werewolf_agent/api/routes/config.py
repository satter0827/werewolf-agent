"""Public runtime configuration route."""

from typing import cast

from fastapi import APIRouter, Request

from werewolf_agent.contracts.api import PublicRuntimeConfig

router = APIRouter(tags=["configuration"])


@router.get("/config", response_model=PublicRuntimeConfig)
def get_runtime_config(request: Request) -> PublicRuntimeConfig:
    """Return only values safe to expose to every browser."""
    return cast(PublicRuntimeConfig, request.app.state.public_runtime_config)
