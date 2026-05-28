"""Public stateless services for provider-independent decisions."""

from __future__ import annotations

import random

from werewolf_agent.domain.llm.models import AgentDecision, AgentObservation, FakeLlmConfig
from werewolf_agent.domain.llm.rules.fake_llm import choose_fake_llm_decision


def choose_decision(
    player_id: str,
    observation: AgentObservation,
    *,
    config: FakeLlmConfig,
    rng: random.Random,
) -> AgentDecision:
    """Return one FakeLLM decision from visible player context."""
    return choose_fake_llm_decision(player_id, observation, config=config, rng=rng)


__all__ = ["choose_decision"]
