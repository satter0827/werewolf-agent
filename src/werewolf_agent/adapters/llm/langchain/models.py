"""LangChain-backed decision services for visible player observations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict

from pydantic import BaseModel

from werewolf_agent.agents.models import (
    AgentActionType,
    AgentDecision,
    AgentObservation,
)


class _ModelDecisionPayload(BaseModel):
    """Minimal structured-output payload requested from compatible chat models."""

    type: str | None = None
    target_id: str | None = None
    message: str | None = None
    reason: str = ""


class _DecisionGraphState(TypedDict, total=False):
    player_id: str
    agent_strategy_id: str
    decision_graph_id: str
    observation: AgentObservation
    action_type: AgentActionType
    target_id: str | None
    prompt_value: Any
    prompt_messages: list[Mapping[str, object]]
    raw_output: object
    decision: AgentDecision
    validation_status: str
    validation_error: str
    fallback_reason: str
    role_hint: str
    target_rankings: dict[str, list[str]]
    invoke_error_payload: Mapping[str, object]
    graph_node: str
    route: str
    repair_attempted: bool
    started_at: float
