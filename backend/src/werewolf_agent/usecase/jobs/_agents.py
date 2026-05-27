"""Private agent adapters used by game jobs."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from werewolf_agent.domain.models import Action, Observation
from werewolf_agent.domain.service import choose_dummy_action


class _DummyAgent:
    """Seeded dummy agent that returns structured actions without a provider call."""

    def __init__(
        self,
        player_id: str,
        *,
        rng: random.Random | None = None,
        speech_templates: Sequence[str] | None = None,
    ) -> None:
        self.player_id = player_id
        self._rng = rng or random.Random()
        self._speech_templates = tuple(speech_templates) if speech_templates is not None else None

    def act(self, observation: Observation) -> Action:
        """Return one structured action for the current observation."""
        if self._speech_templates:
            return choose_dummy_action(
                self.player_id,
                observation,
                rng=self._rng,
                speech_templates=self._speech_templates,
            )
        return choose_dummy_action(self.player_id, observation, rng=self._rng)


@dataclass(frozen=True)
class _DummyAgentFactory:
    """Create deterministic dummy agents for automated MVP game runs."""

    def create(self, player_id: str, *, seed: int) -> _DummyAgent:
        """Create one dummy agent with an injected deterministic seed."""
        return _DummyAgent(player_id, rng=random.Random(seed))
