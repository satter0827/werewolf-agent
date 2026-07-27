"""Deterministic player generation for complete game setups."""

from __future__ import annotations

import random
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from werewolf_agent.application.randomness import namespace_seed
from werewolf_agent.application.setup_document import PlayerGenerationDefinition


class PlayerProfile(BaseModel):
    """Generated runtime profile stored with one normalized game command."""

    name: str
    age: int = Field(ge=18, le=120)
    gender: str
    personality: str
    speaking_style: str
    reasoning_style: str
    risk_tolerance: str
    evidence_focus: str

    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True)
class GeneratedPlayer:
    """One generated seat and its complete private profile."""

    player_id: str
    profile: PlayerProfile

    def public_payload(self) -> dict[str, object]:
        """Return only fields safe to show before the game starts."""
        return {
            "player_id": self.player_id,
            "name": self.profile.name,
            "age": self.profile.age,
            "gender": self.profile.gender,
            "personality": self.profile.personality,
            "speaking_style": self.profile.speaking_style,
        }

    def private_payload(self) -> dict[str, object]:
        """Return the complete profile stored in the immutable game command."""
        return {
            "player_id": self.player_id,
            **self.profile.model_dump(mode="json", exclude={"enabled"}),
        }


def generate_players(
    definition: PlayerGenerationDefinition,
    *,
    player_count: int,
    seed: int,
) -> tuple[GeneratedPlayer, ...]:
    """Compose a fresh deterministic roster from independent component pools."""
    if player_count > len(definition.identities):
        raise ValueError("player identity candidates are fewer than player_count")
    identities = list(definition.identities)
    personas = list(definition.public_personas)
    strategies = list(definition.private_strategies)
    roster_seed = namespace_seed(seed, "roster")
    random.Random(namespace_seed(roster_seed, "identity")).shuffle(identities)
    random.Random(namespace_seed(roster_seed, "persona")).shuffle(personas)
    random.Random(namespace_seed(roster_seed, "strategy")).shuffle(strategies)
    age_rng = random.Random(namespace_seed(roster_seed, "age"))
    generated: list[GeneratedPlayer] = []
    for index, identity in enumerate(identities[:player_count]):
        persona = personas[index % len(personas)]
        strategy = strategies[index % len(strategies)]
        generated.append(
            GeneratedPlayer(
                player_id=f"p{index + 1}",
                profile=PlayerProfile(
                    name=identity.name,
                    age=age_rng.randint(identity.age_min, identity.age_max),
                    gender=identity.gender,
                    personality=persona.personality,
                    speaking_style=persona.speaking_style,
                    reasoning_style=strategy.reasoning_style,
                    risk_tolerance=strategy.risk_tolerance,
                    evidence_focus=strategy.evidence_focus,
                ),
            )
        )
    return tuple(generated)


def profiles_by_player(players: tuple[GeneratedPlayer, ...]) -> dict[str, PlayerProfile]:
    """Return complete generated profiles keyed by stable seat ID."""
    return {player.player_id: player.profile for player in players}


__all__ = ["GeneratedPlayer", "PlayerProfile", "generate_players", "profiles_by_player"]
