"""Ports for future real LLM decision providers."""

from __future__ import annotations

from typing import Protocol

from werewolf_agent.domain.llm.models import AgentDecision, AgentObservation


class LlmDecisionProvider(Protocol):
    """Provider boundary for turning visible player context into one decision."""

    def choose_decision(self, player_id: str, observation: AgentObservation) -> AgentDecision:
        """Return one validated decision for a visible player observation.

        Args:
            player_id: Player requesting a decision.
            observation: Provider-independent context visible to that player.

        Returns:
            Structured decision that can be adapted to a game action.
        """


__all__ = ["LlmDecisionProvider"]
