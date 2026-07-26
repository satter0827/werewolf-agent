"""Commands and queries accepted by application operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from werewolf_agent.application.constants import (
    MIN_PAGE_LIMIT,
    MIN_PAGE_OFFSET,
    MIN_VERSION,
    NarrationMode,
)
from werewolf_agent.application.definitions import (
    CustomCharacterDefinition,
    CustomRoleDefinition,
    LocalRulesDefinition,
)
from werewolf_agent.application.messages import (
    MESSAGE_CHARACTER_ASSIGNMENTS_KEYS_MUST_MATCH_PLAYERS,
    MESSAGE_CHARACTER_ASSIGNMENTS_VALUES_MUST_BE_UNIQUE,
    MESSAGE_CUSTOM_CHARACTER_IDS_MUST_BE_UNIQUE,
    MESSAGE_CUSTOM_ROLE_IDS_MUST_BE_UNIQUE,
    MESSAGE_MANUAL_PLAYER_ID_MUST_MATCH_PLAYERS,
    MESSAGE_PLAYER_COUNT_AT_LEAST_ONE,
)
from werewolf_agent.application.models.base import ApplicationModel
from werewolf_agent.application.models.results import GameEventCreate
from werewolf_agent.contracts import GamePhase, GameStatus, RoleCount, RoleId
from werewolf_agent.contracts.validation import generated_player_ids, non_blank

if TYPE_CHECKING:
    from werewolf_agent.domain import Game, GameEvent

EventVisibility = Literal["public", "player_private", "debug"]
ActionTypeId = str


class CreateGameCommand(ApplicationModel):
    """Command for creating one game."""

    seed: int | None = None
    scenario_id: str | None = None
    setup_preset_id: str | None = None
    narration_mode: NarrationMode
    role_counts: dict[RoleId, RoleCount]
    rules: LocalRulesDefinition
    manual_player_id: str | None = None
    character_assignments: dict[str, str] = Field(default_factory=dict)
    custom_roles: list[CustomRoleDefinition] = Field(default_factory=list)
    custom_characters: list[CustomCharacterDefinition] = Field(default_factory=list)
    llm_mode: Literal["fake", "paid"] = "fake"

    @field_validator("role_counts")
    @classmethod
    def validate_role_counts(cls, value: dict[RoleId, RoleCount]) -> dict[RoleId, RoleCount]:
        """Return role counts keyed by normalized role id."""
        normalized = {
            non_blank(str(role_id), "role_counts key"): count for role_id, count in value.items()
        }
        if sum(normalized.values()) < 1:
            raise ValueError(MESSAGE_PLAYER_COUNT_AT_LEAST_ONE)
        return normalized

    @field_validator("manual_player_id")
    @classmethod
    def validate_manual_player_id(cls, value: str | None) -> str | None:
        """Return a stripped optional manual player id."""
        if value is None:
            return None
        return non_blank(value, "manual_player_id")

    @field_validator("scenario_id", "setup_preset_id")
    @classmethod
    def validate_optional_ids(cls, value: str | None) -> str | None:
        """Return stripped optional setup ids."""
        if value is None:
            return None
        return non_blank(value, "setup id")

    @field_validator("character_assignments")
    @classmethod
    def validate_character_assignments(cls, value: dict[str, str]) -> dict[str, str]:
        """Return character assignments keyed by generated player id."""
        return {
            non_blank(str(player_id), "character assignment player id"): non_blank(
                character_id,
                "character assignment id",
            )
            for player_id, character_id in value.items()
        }

    @model_validator(mode="after")
    def validate_manual_player_within_generated_seats(self) -> Self:
        """Ensure the requested manual seat exists in the generated table."""
        valid_player_ids = generated_player_ids(self.player_count)
        if self.manual_player_id is not None and self.manual_player_id not in valid_player_ids:
            raise ValueError(MESSAGE_MANUAL_PLAYER_ID_MUST_MATCH_PLAYERS)
        unknown_assignments = sorted(set(self.character_assignments) - valid_player_ids)
        if unknown_assignments:
            raise ValueError(MESSAGE_CHARACTER_ASSIGNMENTS_KEYS_MUST_MATCH_PLAYERS)
        assigned_character_ids = list(self.character_assignments.values())
        if len(set(assigned_character_ids)) != len(assigned_character_ids):
            raise ValueError(MESSAGE_CHARACTER_ASSIGNMENTS_VALUES_MUST_BE_UNIQUE)
        custom_role_ids = [definition.id for definition in self.custom_roles]
        if len(set(custom_role_ids)) != len(custom_role_ids):
            raise ValueError(MESSAGE_CUSTOM_ROLE_IDS_MUST_BE_UNIQUE)
        custom_character_ids = [definition.id for definition in self.custom_characters]
        if len(set(custom_character_ids)) != len(custom_character_ids):
            raise ValueError(MESSAGE_CUSTOM_CHARACTER_IDS_MUST_BE_UNIQUE)
        return self

    @property
    def player_count(self) -> int:
        """Return the player count derived from role counts."""
        return sum(self.role_counts.values())


class GetGameQuery(ApplicationModel):
    """Query for loading one game."""

    game_id: str | UUID

    model_config = ConfigDict(extra="forbid", frozen=True)


class GetGameRevealQuery(ApplicationModel):
    """Query for loading full observer-only game information."""

    game_id: str | UUID

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceGameCommand(ApplicationModel):
    """Command for advancing one game by one business step."""

    game_id: str | UUID
    expected_version: int | None = Field(default=None, ge=MIN_VERSION)

    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True)
class PreparedAdvanceGame:
    """Prepared immutable input for one advance computation."""

    game_id: str
    version: int
    seed: int | None
    config: dict[str, Any]
    game: Game
    created_at: datetime
    domain_events: tuple[GameEvent, ...] = ()


class ComputedAdvanceGame(ApplicationModel):
    """Computed advance result waiting for version-checked persistence."""

    game_id: str
    expected_version: int
    status: GameStatus
    phase: GamePhase
    day: int
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    pending_actions: dict[str, Any]
    events: list[GameEventCreate]

    model_config = ConfigDict(extra="forbid", frozen=True)


class GetPlayerObservationQuery(ApplicationModel):
    """Query for one player's private observation."""

    game_id: str | UUID
    player_id: str
    trusted_user_id: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerActionCommand(ApplicationModel):
    """Command for submitting one manual player action."""

    game_id: str | UUID
    player_id: str
    trusted_user_id: str | None = None
    type: ActionTypeId
    target_id: str | None = None
    message: str | None = None
    reason: str = ""
    expected_version: int | None = Field(default=None, ge=MIN_VERSION)

    model_config = ConfigDict(extra="forbid", frozen=True)


class ListGamesQuery(ApplicationModel):
    """Query for listing public games."""

    status: GameStatus | None = None
    limit: int | None = Field(default=None, ge=MIN_PAGE_LIMIT)
    offset: int = Field(default=MIN_PAGE_OFFSET, ge=MIN_PAGE_OFFSET)

    model_config = ConfigDict(extra="forbid", frozen=True)


class ListTimelineQuery(ApplicationModel):
    """Query for listing public timeline items after a sequence cursor."""

    game_id: str | UUID
    after: int = Field(default=MIN_PAGE_OFFSET, ge=MIN_PAGE_OFFSET)
    limit: int | None = Field(default=None, ge=MIN_PAGE_LIMIT)

    model_config = ConfigDict(extra="forbid", frozen=True)
