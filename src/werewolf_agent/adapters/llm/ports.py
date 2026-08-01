"""Ports for automated player decision providers."""

from __future__ import annotations

from typing import Protocol

from werewolf_agent.adapters.llm.models import (
    AgentDecision,
    AgentObservation,
    ModelRequest,
    ModelResponse,
)


class DecisionModel(Protocol):
    """Provider-independent boundary for one chat-model invocation."""

    def invoke(self, request: ModelRequest) -> ModelResponse:
        """Return one normalized model response."""


class PlayerAgent(Protocol):
    """Provider boundary for turning visible player context into one decision."""

    def choose_decision(
        self,
        player_id: str,
        observation: AgentObservation,
        *,
        timeout_seconds: float | None = None,
    ) -> AgentDecision:
        """Return one validated decision for a visible player observation.

        Args:
            player_id: Player requesting a decision.
            observation: Provider-independent context visible to that player.

        Returns:
            Structured decision that can be adapted to a game action.

        """


__all__ = ["DecisionModel", "PlayerAgent"]
