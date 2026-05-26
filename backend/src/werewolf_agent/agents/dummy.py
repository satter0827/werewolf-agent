"""Deterministic dummy agent implementation."""

from __future__ import annotations

import random
from collections.abc import Sequence

from werewolf_agent.domain.models import Action, Observation
from werewolf_agent.domain.service import choose_dummy_action


class DummyAgent:
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
        return choose_dummy_action(
            self.player_id,
            observation,
            rng=self._rng,
        )


__all__ = ["DummyAgent"]
