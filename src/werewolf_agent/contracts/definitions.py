"""contracts definition models."""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    MESSAGE_LOCAL_RULE_TIE_RULE_EXACTLY_ONE,
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
    enable_no_elimination_on_tie: bool
    enable_random_elimination_on_tie: bool
    allow_knight_self_guard: bool
    allow_knight_repeat_guard: bool
    allow_seer_self_inspect: bool
    allow_werewolf_friendly_fire: bool
    reveal_role_on_death: bool
    require_all_actions_before_advance: bool = True

    @model_validator(mode="after")
    def validate_tie_resolution(self) -> Self:
        """Ensure one tie-resolution behavior is active."""
        enabled = [
            self.enable_no_elimination_on_tie,
            self.enable_random_elimination_on_tie,
        ]
        if enabled.count(True) != 1:
            raise ValueError(MESSAGE_LOCAL_RULE_TIE_RULE_EXACTLY_ONE)
        return self


class CustomRoleDefinition(_DefinitionModel):
    """Session-scoped role definition supplied by a game API caller."""

    id: str
    name: str
    faction: str
    abilities: list[str] = Field(default_factory=list)
    description: str = ""
    difficulty: int = Field(default=MIN_DIFFICULTY, ge=MIN_DIFFICULTY, le=MAX_DIFFICULTY)

    @field_validator("id", "name", "faction")
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
