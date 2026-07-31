"""Allowlist-only conversion from application results to HTTP contracts."""

from __future__ import annotations

from pydantic import BaseModel

from werewolf_agent.application import QueuedOperation
from werewolf_agent.contracts.api import OperationResponse
from werewolf_agent.contracts.mapping import wire_model
from werewolf_agent.contracts.schemas import (
    AvailableActionDescriptor,
    GameListResponse,
    GameResponse,
    GameRevealResponse,
    GameTimelineResponse,
    PlayerObservation,
    PlayerObservationHistory,
    PlayerObservationOutcome,
    PlayerObservationResponse,
    PlayerObservationSpeech,
    PlayerObservationVote,
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
    payload = source.model_dump(mode="json")
    observation = payload["observation"]
    legal_targets = observation.get("legal_targets", {})
    actions: list[AvailableActionDescriptor] = []
    for item in observation.get("available_actions", []):
        ability_id = item.get("ability_id")
        key = f"{item['type']}:{ability_id}" if ability_id is not None else item["type"]
        actions.append(
            AvailableActionDescriptor(
                key=key,
                type=item["type"],
                ability_id=ability_id,
                legal_target_ids=legal_targets.get(key, []),
                message_required=item["type"] == "speech",
            )
        )
    history = observation.get("history", {})
    win_result = observation.get("win_result")
    return PlayerObservationResponse(
        game_id=payload["game_id"],
        player_id=payload["player_id"],
        observation=PlayerObservation(
            phase=observation["phase"],
            day=observation["day"],
            me=observation["me"],
            players=observation["players"],
            known_roles=observation.get("known_roles", {}),
            known_factions=observation.get("known_factions", {}),
            available_actions=actions,
            history=PlayerObservationHistory(
                speeches=[
                    PlayerObservationSpeech.model_validate(
                        {
                            key: speech[key]
                            for key in (
                                "day",
                                "player_id",
                                "message",
                                "focus_id",
                                "evidence_id",
                            )
                            if key in speech
                        }
                    )
                    for speech in history.get("speeches", [])
                ],
                votes=[
                    PlayerObservationVote.model_validate(vote) for vote in history.get("votes", [])
                ],
            ),
            win_result=(
                None
                if win_result is None
                else PlayerObservationOutcome.model_validate(
                    {
                        key: win_result[key]
                        for key in ("winner", "reason", "day")
                        if key in win_result
                    }
                )
            ),
        ),
    )


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
