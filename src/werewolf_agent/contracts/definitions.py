"""contracts definition models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from werewolf_agent.contracts.constants import (
    MAX_CHARACTER_AGE,
    MAX_DAY_SPEECH_LIMIT_PER_PLAYER,
    MAX_DIFFICULTY,
    MIN_CHARACTER_AGE,
    MIN_DAY_SPEECH_LIMIT_PER_PLAYER,
    MIN_DIFFICULTY,
)
from werewolf_agent.contracts.messages import (
    MESSAGE_CUSTOM_ROLE_ABILITIES_MUST_BE_UNIQUE,
)
from werewolf_agent.contracts.validation import non_blank


class _DefinitionModel(BaseModel):
    """Base model for immutable wire definitions."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class LocalRulesDefinition(_DefinitionModel):
    """Local rule flags used by the game core."""

    day_speech_limit_per_player: int = Field(
        ge=MIN_DAY_SPEECH_LIMIT_PER_PLAYER,
        le=MAX_DAY_SPEECH_LIMIT_PER_PLAYER,
    )
    allow_self_vote: bool
    allow_vote_revision: bool
    allow_night_action_revision: bool
    enable_first_night_attack: bool
    vote_tie_resolution: Literal["no_elimination", "random_elimination", "revote"]
    wolf_attack_tie_resolution: Literal["random_target", "no_attack"]
    seer_result_detail: Literal["faction", "role"]
    medium_result_detail: Literal["faction", "role"]
    starting_phase: Literal["night", "day_discussion"]
    allow_knight_self_guard: bool
    allow_knight_repeat_guard: bool
    allow_seer_self_inspect: bool
    allow_werewolf_friendly_fire: bool
    reveal_role_on_death: bool
    require_all_actions_before_advance: bool = True


class CustomRoleDefinition(_DefinitionModel):
    """Session-scoped role definition supplied by a game API caller."""

    id: str
    name: str
    identity_faction: Literal["village", "werewolf", "fox"]
    victory_team: Literal["village", "werewolf", "fox"]
    objective: str
    abilities: list[str] = Field(default_factory=list)
    description: str = ""
    difficulty: int = Field(default=MIN_DIFFICULTY, ge=MIN_DIFFICULTY, le=MAX_DIFFICULTY)

    @field_validator("id", "name", "objective")
    @classmethod
    def validate_non_blank_text(cls, value: str, info: Any) -> str:
        """Return normalized custom role text."""
        return non_blank(value, str(info.field_name))

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        """Return normalized optional role description."""
        return value.strip()

    @field_validator("abilities")
    @classmethod
    def validate_abilities(cls, value: list[str]) -> list[str]:
        """Return normalized unique ability ids."""
        abilities = [non_blank(item, "ability") for item in value]
        if len(set(abilities)) != len(abilities):
            raise ValueError(MESSAGE_CUSTOM_ROLE_ABILITIES_MUST_BE_UNIQUE)
        return abilities


class CustomCharacterDefinition(_DefinitionModel):
    """Session-scoped character definition supplied by a game API caller."""

    id: str
    name: str
    age: int = Field(ge=MIN_CHARACTER_AGE, le=MAX_CHARACTER_AGE)
    gender: str
    personality: str
    speaking_style: str
    reasoning_style: str
    risk_tolerance: str

    @field_validator(
        "id",
        "name",
        "gender",
        "personality",
        "speaking_style",
        "reasoning_style",
        "risk_tolerance",
    )
    @classmethod
    def validate_non_blank_text(cls, value: str, info: Any) -> str:
        """Return normalized custom character text."""
        return non_blank(value, str(info.field_name))
