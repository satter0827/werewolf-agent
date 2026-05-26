"""Agent factories used by game use cases."""

from __future__ import annotations

import random
from dataclasses import dataclass

from werewolf_agent.domain.models import DummyAgent


@dataclass(frozen=True)
class DummyAgentFactory:
    """Create deterministic dummy agents for automated MVP game runs."""

    def create(self, player_id: str, *, seed: int) -> DummyAgent:
        """Create one dummy agent with an injected deterministic seed."""
        return DummyAgent(player_id, rng=random.Random(seed))
