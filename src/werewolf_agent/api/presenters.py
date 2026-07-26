"""Allowlist-only conversion from application results to HTTP contracts."""

from __future__ import annotations

from pydantic import BaseModel

from werewolf_agent.application.operations import QueuedOperation
from werewolf_agent.contracts.api import OperationResponse
from werewolf_agent.contracts.mapping import wire_model
from werewolf_agent.contracts.schemas import (
    GameListResponse,
    GameResponse,
    GameRevealResponse,
    GameTimelineResponse,
    PlayerObservationResponse,
    ProblemDetails,
)


def wire(model_type: type[BaseModel], source: BaseModel) -> BaseModel:
    """Validate one application result against an independent wire model."""
    return wire_model(model_type, source)


def game_response(source: BaseModel) -> GameResponse:
    """Return allowlisted public game state."""
    return wire_model(GameResponse, source)


def game_list_response(source: BaseModel) -> GameListResponse:
    """Return allowlisted public game summaries."""
    return wire_model(GameListResponse, source)


def timeline_response(source: BaseModel) -> GameTimelineResponse:
    """Return allowlisted public timeline."""
    return wire_model(GameTimelineResponse, source)


def observation_response(source: BaseModel) -> PlayerObservationResponse:
    """Return allowlisted private player observation."""
    return wire_model(PlayerObservationResponse, source)


def reveal_response(source: BaseModel) -> GameRevealResponse:
    """Return allowlisted administrator reveal."""
    return wire_model(GameRevealResponse, source)


def operation_response(source: QueuedOperation) -> OperationResponse:
    """Return an operation without owner identity or request payload."""
    problem = ProblemDetails.model_validate(source.error) if source.error else None
    return OperationResponse(
        operation_id=source.operation_id,
        operation_type=source.operation_type,
        status=source.status,
        game_id=source.game_id,
        expected_version=source.expected_version,
        result=source.result,
        error=problem,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


__all__ = [
    "game_list_response",
    "game_response",
    "observation_response",
    "operation_response",
    "reveal_response",
    "timeline_response",
]
