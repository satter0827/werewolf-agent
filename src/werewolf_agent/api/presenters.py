"""Allowlist-only conversion from application results to HTTP contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from werewolf_agent.application import QueuedOperation, SavedSetupRevision
from werewolf_agent.contracts.api import OperationResponse, SavedSetupRevisionResponse
from werewolf_agent.contracts.mapping import wire_model
from werewolf_agent.contracts.schemas import (
    AvailableActionDescriptor,
    DiscussionRoundDescriptor,
    GameListResponse,
    GameResponse,
    GameRevealResponse,
    GameSetupDocumentRequest,
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


def observation_response(
    source: BaseModel,
    *,
    api_text_max_chars: int | None = None,
) -> PlayerObservationResponse:
    """Return allowlisted private player observation."""
    payload = source.model_dump(mode="json")
    observation = payload["observation"]
    legal_targets = observation.get("legal_targets", {})
    legal_evidence = observation.get("legal_evidence", {})
    action_text_limits = observation.get("action_text_limits", {})
    actions: list[AvailableActionDescriptor] = []
    for item in observation.get("available_actions", []):
        ability_id = item.get("ability_id")
        key = f"{item['type']}:{ability_id}" if ability_id is not None else item["type"]
        configured_limit = action_text_limits.get(key)
        effective_limit = (
            min(configured_limit, api_text_max_chars)
            if isinstance(configured_limit, int) and api_text_max_chars is not None
            else configured_limit
        )
        actions.append(
            AvailableActionDescriptor(
                key=key,
                type=item["type"],
                ability_id=ability_id,
                legal_target_ids=legal_targets.get(key, []),
                evidence_options=legal_evidence.get(key, []),
                message_required=item["type"] == "speech",
                message_max_chars=(effective_limit if item["type"] == "speech" else None),
                reason_max_chars=(effective_limit if item["type"] == "vote" else None),
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
                                "speech_id",
                                "round_id",
                                "round_kind",
                                "player_id",
                                "utterance",
                                "topic_id",
                                "position",
                                "relation",
                                "evidence_id",
                                "response_to_id",
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
            discussion_round=_discussion_round_descriptor(observation, payload["player_id"]),
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


def _discussion_round_descriptor(
    observation: dict[str, Any],
    player_id: str,
) -> DiscussionRoundDescriptor | None:
    """Active setupと公開履歴からserver-authorized response候補を返す."""
    round_ = observation.get("discussion_round")
    if not isinstance(round_, dict):
        return None
    relations = [str(item) for item in observation.get("allowed_discussion_relations", [])]
    speeches = {
        str(item["speech_id"]): item for item in observation.get("history", {}).get("speeches", [])
    }
    response_options: list[dict[str, str]] = []
    for reference_id in round_.get("reference_ids", []):
        referenced = speeches.get(str(reference_id))
        if referenced is None or referenced.get("player_id") == player_id:
            continue
        topic_id = str(referenced["topic_id"])
        referenced_position = str(referenced["position"])
        prior = next(
            (
                item
                for item in reversed(tuple(speeches.values()))
                if item.get("player_id") == player_id and item.get("topic_id") == topic_id
            ),
            None,
        )
        for relation in relations:
            positions: tuple[str, ...] = ()
            if relation == "answer" and referenced_position == "undecided":
                positions = ("support", "oppose")
            elif relation == "support":
                positions = (referenced_position,)
            elif relation == "challenge" and referenced_position in {"support", "oppose"}:
                positions = ("oppose" if referenced_position == "support" else "support",)
            elif relation == "revise" and prior is not None:
                positions = tuple(
                    item
                    for item in ("support", "oppose", "undecided")
                    if item != prior.get("position")
                )
            response_options.extend(
                {
                    "response_to_id": str(reference_id),
                    "evidence_id": str(reference_id),
                    "topic_id": topic_id,
                    "position": position,
                    "relation": relation,
                }
                for position in positions
            )
    return DiscussionRoundDescriptor.model_validate(
        {
            key: round_[key]
            for key in (
                "round_id",
                "cycle",
                "kind",
                "submission_mode",
                "actor_order",
                "cursor",
                "reference_ids",
            )
        }
        | {"allowed_relations": relations, "response_options": response_options}
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


def saved_setup_revision_response(source: SavedSetupRevision) -> SavedSetupRevisionResponse:
    """Return one setup revision after explicitly crossing the domain document boundary."""
    return SavedSetupRevisionResponse(
        setup_id=source.setup_id,
        display_name=source.display_name,
        revision=source.revision,
        document=GameSetupDocumentRequest.model_validate(source.document.to_mapping()),
        setup_checksum=source.setup_checksum,
        mechanics_checksum=source.mechanics_checksum,
        created_at=source.created_at,
    )


__all__ = [
    "game_list_response",
    "game_response",
    "observation_response",
    "operation_response",
    "reveal_response",
    "saved_setup_revision_response",
    "timeline_response",
]
