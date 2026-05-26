"""Agent factories used by game use cases."""

from __future__ import annotations

import random
from dataclasses import dataclass

from werewolf_agent.agents.fake_llm import FakeLlmAgent


@dataclass(frozen=True)
class DummyAgentFactory:
    """Create deterministic dummy agents for automated MVP game runs."""

    def create(self, player_id: str, *, seed: int) -> FakeLlmAgent:
        """Create one dummy agent with an injected deterministic seed."""
        return FakeLlmAgent(player_id, rng=random.Random(seed))
