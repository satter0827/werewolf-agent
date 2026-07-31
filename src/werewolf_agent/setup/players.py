"""第三者依存を持たない決定的なplayer roster生成を定義する."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

from werewolf_agent.setup.randomness import namespace_seed

RiskTolerance = Literal["low", "medium", "high"]


def _text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be blank")
    return normalized


@dataclass(frozen=True)
class PlayerIdentityDefinition:
    """生成rosterごとに一度使用する公開identity候補を表す."""

    name: str
    age_min: int
    age_max: int
    gender: str

    def __post_init__(self) -> None:
        """公開identityのtextと年齢範囲を検証する."""
        object.__setattr__(self, "name", _text(self.name, "name"))
        object.__setattr__(self, "gender", _text(self.gender, "gender"))
        if any(
            not isinstance(age, int) or isinstance(age, bool)
            for age in (self.age_min, self.age_max)
        ):
            raise TypeError("ages must be integers")
        if not 18 <= self.age_min <= self.age_max <= 120:
            raise ValueError("ages must satisfy 18 <= age_min <= age_max <= 120")


@dataclass(frozen=True)
class PublicPersonaDefinition:
    """Identityと組み合わせる公開行動fieldを表す."""

    personality: str
    speaking_style: str

    def __post_init__(self) -> None:
        """公開personaのtextを検証する."""
        object.__setattr__(self, "personality", _text(self.personality, "personality"))
        object.__setattr__(self, "speaking_style", _text(self.speaking_style, "speaking_style"))


@dataclass(frozen=True)
class PrivateStrategyDefinition:
    """割当済みagentだけへ渡すprivate strategyを表す."""

    reasoning_style: str
    risk_tolerance: RiskTolerance
    evidence_focus: str

    def __post_init__(self) -> None:
        """Private strategyのtextとrisk区分を検証する."""
        object.__setattr__(
            self,
            "reasoning_style",
            _text(self.reasoning_style, "reasoning_style"),
        )
        object.__setattr__(
            self,
            "evidence_focus",
            _text(self.evidence_focus, "evidence_focus"),
        )
        if self.risk_tolerance not in {"low", "medium", "high"}:
            raise ValueError("risk_tolerance must be low, medium, or high")


@dataclass(frozen=True)
class PlayerGenerationDefinition:
    """ゲームごとにrosterを構成する決定的なcomponent poolを表す."""

    identities: tuple[PlayerIdentityDefinition, ...]
    public_personas: tuple[PublicPersonaDefinition, ...]
    private_strategies: tuple[PrivateStrategyDefinition, ...]

    def __post_init__(self) -> None:
        """Component poolをimmutableなtupleへ正規化して検証する."""
        object.__setattr__(self, "identities", tuple(self.identities))
        object.__setattr__(self, "public_personas", tuple(self.public_personas))
        object.__setattr__(self, "private_strategies", tuple(self.private_strategies))
        if not self.identities or not self.public_personas or not self.private_strategies:
            raise ValueError("player generation pools must not be empty")
        names = tuple(identity.name for identity in self.identities)
        if len(names) != len(set(names)):
            raise ValueError("player identity names must be unique")


@dataclass(frozen=True)
class PlayerProfile:
    """生成済みplayerの公開personaとprivate strategyを表す."""

    name: str
    age: int
    gender: str
    personality: str
    speaking_style: str
    reasoning_style: str
    risk_tolerance: RiskTolerance
    evidence_focus: str

    def __post_init__(self) -> None:
        """生成済みprofileの全fieldを検証する."""
        for field_name in (
            "name",
            "gender",
            "personality",
            "speaking_style",
            "reasoning_style",
            "evidence_focus",
        ):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        if not isinstance(self.age, int) or isinstance(self.age, bool) or not 18 <= self.age <= 120:
            raise ValueError("age must be an integer from 18 through 120")
        if self.risk_tolerance not in {"low", "medium", "high"}:
            raise ValueError("risk_tolerance must be low, medium, or high")

    def to_mapping(self) -> dict[str, object]:
        """JSON互換の完全profileを返す."""
        return {
            "name": self.name,
            "age": self.age,
            "gender": self.gender,
            "personality": self.personality,
            "speaking_style": self.speaking_style,
            "reasoning_style": self.reasoning_style,
            "risk_tolerance": self.risk_tolerance,
            "evidence_focus": self.evidence_focus,
        }


@dataclass(frozen=True)
class GeneratedPlayer:
    """安定したseat IDと生成済みprofileを表す."""

    player_id: str
    profile: PlayerProfile

    def __post_init__(self) -> None:
        """Seat IDを正規化して検証する."""
        object.__setattr__(self, "player_id", _text(self.player_id, "player_id"))

    def public_payload(self) -> dict[str, object]:
        """ゲーム開始前に公開できるfieldだけを返す."""
        return {
            "player_id": self.player_id,
            "name": self.profile.name,
            "age": self.profile.age,
            "gender": self.profile.gender,
            "personality": self.profile.personality,
            "speaking_style": self.profile.speaking_style,
        }

    def private_payload(self) -> dict[str, object]:
        """正規化commandへ保存する完全profileを返す."""
        return {"player_id": self.player_id, **self.profile.to_mapping()}


def generate_players(
    definition: PlayerGenerationDefinition,
    *,
    player_count: int,
    seed: int,
) -> tuple[GeneratedPlayer, ...]:
    """独立したcomponent poolから決定的なrosterを生成する."""
    if not isinstance(player_count, int) or isinstance(player_count, bool) or player_count < 1:
        raise ValueError("player_count must be a positive integer")
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
    return tuple(
        GeneratedPlayer(
            player_id=f"p{index + 1}",
            profile=PlayerProfile(
                name=identity.name,
                age=age_rng.randint(identity.age_min, identity.age_max),
                gender=identity.gender,
                personality=personas[index % len(personas)].personality,
                speaking_style=personas[index % len(personas)].speaking_style,
                reasoning_style=strategies[index % len(strategies)].reasoning_style,
                risk_tolerance=strategies[index % len(strategies)].risk_tolerance,
                evidence_focus=strategies[index % len(strategies)].evidence_focus,
            ),
        )
        for index, identity in enumerate(identities[:player_count])
    )


def profiles_by_player(players: tuple[GeneratedPlayer, ...]) -> dict[str, PlayerProfile]:
    """安定したseat IDをkeyに完全profileを返す."""
    return {player.player_id: player.profile for player in players}


__all__ = [
    "GeneratedPlayer",
    "PlayerGenerationDefinition",
    "PlayerIdentityDefinition",
    "PlayerProfile",
    "PrivateStrategyDefinition",
    "PublicPersonaDefinition",
    "RiskTolerance",
    "generate_players",
    "profiles_by_player",
]
