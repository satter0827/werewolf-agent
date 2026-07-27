"""Commands and queries accepted by application operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from werewolf_agent.application.checksums import checksum_payload
from werewolf_agent.application.constants import (
    DEFAULT_DELIBERATION_LEVEL,
    MIN_PAGE_LIMIT,
    MIN_PAGE_OFFSET,
    MIN_VERSION,
    DeliberationLevel,
)
from werewolf_agent.application.messages import (
    MESSAGE_MANUAL_PLAYER_ID_MUST_MATCH_PLAYERS,
)
from werewolf_agent.application.models.base import ApplicationModel
from werewolf_agent.application.models.results import GameEventCreate
from werewolf_agent.application.setup_document import GameSetupDocument
from werewolf_agent.application.types import GamePhase, GameStatus
from werewolf_agent.application.validation import generated_player_ids, non_blank

if TYPE_CHECKING:
    from werewolf_agent.domain import Game, GameEvent

EventVisibility = Literal["public", "player_private", "debug"]
ActionTypeId = str


class GeneratedPlayerInput(ApplicationModel):
    """Complete generated player profile embedded in a create command."""

    player_id: str
    name: str
    age: int = Field(ge=18, le=120)
    gender: str
    personality: str
    speaking_style: str
    reasoning_style: str
    risk_tolerance: str
    evidence_focus: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class CreateGameCommand(ApplicationModel):
    """Command for creating one game."""

    seed: int
    setup: GameSetupDocument
    players: tuple[GeneratedPlayerInput, ...]
    setup_checksum: str
    mechanics_checksum: str
    roster_checksum: str
    manual_player_id: str | None = None
    llm_mode: Literal["fake", "paid"] = "fake"
    deliberation_level: DeliberationLevel = DEFAULT_DELIBERATION_LEVEL

    @field_validator("manual_player_id")
    @classmethod
    def validate_manual_player_id(cls, value: str | None) -> str | None:
        """Return a stripped optional manual player id."""
        if value is None:
            return None
        return non_blank(value, "manual_player_id")

    @model_validator(mode="after")
    def validate_manual_player_within_generated_seats(self) -> Self:
        """Ensure the requested manual seat exists in the generated table."""
        valid_player_ids = generated_player_ids(self.player_count)
        actual_player_ids = {player.player_id for player in self.players}
        if actual_player_ids != valid_player_ids or len(self.players) != self.player_count:
            raise ValueError("generated players must exactly match the configured seats")
        names = [player.name for player in self.players]
        if len(names) != len(set(names)):
            raise ValueError("generated player names must be unique")
        if self.manual_player_id is not None and self.manual_player_id not in valid_player_ids:
            raise ValueError(MESSAGE_MANUAL_PLAYER_ID_MUST_MATCH_PLAYERS)
        expected_checksums = {
            "setup_checksum": checksum_payload(self.setup.model_dump(mode="json")),
            "mechanics_checksum": checksum_payload(self.setup.mechanics.model_dump(mode="json")),
            "roster_checksum": checksum_payload(
                [player.model_dump(mode="json") for player in self.players]
            ),
        }
        for field_name, expected in expected_checksums.items():
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} does not match the normalized command")
        return self

    @property
    def player_count(self) -> int:
        """Return the player count derived from role counts."""
        return sum(self.setup.mechanics.role_counts.values())


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
    ability_id: str | None = None
    target_id: str | None = None
    message: str | None = None
    reason: str = ""
    expected_version: int | None = Field(default=None, ge=MIN_VERSION)

    model_config = ConfigDict(extra="forbid", frozen=True)


class ListGamesQuery(ApplicationModel):
    """Query for listing public games."""

    trusted_user_id: str
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
