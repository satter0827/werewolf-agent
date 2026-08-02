"""Commands and queries accepted by application operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, field_serializer, field_validator, model_validator

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
from werewolf_agent.application.types import GamePhase, GameStatus
from werewolf_agent.application.validation import generated_player_ids, non_blank
from werewolf_agent.domain import CORE_RULE_PACK_ID
from werewolf_agent.setup import GameSetupDocument, checksum_payload

if TYPE_CHECKING:
    from werewolf_agent.domain import Game, GameEvent, GameState

EventVisibility = Literal["public", "player_private", "debug"]
ActionTypeId = str


class GeneratedPlayerInput(ApplicationModel):
    """作成commandへ埋め込む完全な生成player profileを表す."""

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

    def public_payload(self) -> dict[str, object]:
        """公開roster checksumへ含めるprofileだけを返す."""
        return self.model_dump(
            mode="json",
            include={
                "player_id",
                "name",
                "age",
                "gender",
                "personality",
                "speaking_style",
            },
        )


class CreateGameCommand(ApplicationModel):
    """一つのゲームを作成するcommandを表す."""

    seed: int
    setup: GameSetupDocument
    players: tuple[GeneratedPlayerInput, ...]
    setup_checksum: str
    mechanics_checksum: str
    roster_checksum: str
    manual_player_id: str | None = None
    llm_mode: Literal["fake", "paid"] = "fake"
    deliberation_level: DeliberationLevel = DEFAULT_DELIBERATION_LEVEL
    rule_pack_provider_id: str = CORE_RULE_PACK_ID

    @field_serializer("setup")
    def serialize_setup(self, setup: GameSetupDocument) -> dict[str, object]:
        """Immutable setupをJSON互換mappingとして返す."""
        return setup.to_mapping()

    @field_validator("rule_pack_provider_id")
    @classmethod
    def validate_rule_pack_provider_id(cls, value: str) -> str:
        """空白を除去した明示的なRule Pack provider IDを返す."""
        return non_blank(value, "rule_pack_provider_id")

    @field_validator("manual_player_id")
    @classmethod
    def validate_manual_player_id(cls, value: str | None) -> str | None:
        """空白を除去した任意のmanual player IDを返す."""
        if value is None:
            return None
        return non_blank(value, "manual_player_id")

    @model_validator(mode="after")
    def validate_manual_player_within_generated_seats(self) -> Self:
        """要求したmanual seatが生成tableに存在することを検証する."""
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
            "setup_checksum": checksum_payload(self.setup.to_mapping()),
            "mechanics_checksum": checksum_payload(self.setup.mechanics.to_mapping()),
            "roster_checksum": checksum_payload(
                [player.public_payload() for player in self.players]
            ),
        }
        for field_name, expected in expected_checksums.items():
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} does not match the normalized command")
        return self

    @property
    def player_count(self) -> int:
        """役職数から導出したplayer数を返す."""
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
    """一回の進行計算へ渡すimmutableな準備済み入力を表す."""

    game_id: str
    version: int
    seed: int | None
    config: dict[str, Any]
    game: Game
    prepared_state: GameState
    created_at: datetime
    phase_seed: int
    domain_transition_complete: bool = False
    domain_events: tuple[GameEvent, ...] = ()
    domain_actions: tuple[Mapping[str, object], ...] = ()


class ComputedAdvanceGame(ApplicationModel):
    """Version検査付き保存を待つ進行計算結果を表す."""

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


class SpeechActionInput(ApplicationModel):
    """構造化された公開議論手を表すapplication入力."""

    type: Literal["speech"]
    utterance: str
    topic_id: str
    position: Literal["support", "oppose", "undecided"]
    relation: Literal["independent", "answer", "support", "challenge", "revise"]
    evidence_id: str | None = None
    response_to_id: str | None = None


class VoteActionInput(ApplicationModel):
    """公開理由付き投票を表すapplication入力."""

    type: Literal["vote"]
    target_id: str
    reason: str
    evidence_id: str | None = None


class UseAbilityActionInput(ApplicationModel):
    """能力使用を表すapplication入力."""

    type: Literal["use_ability"]
    ability_id: str
    target_id: str | None = None


class PassActionInput(ApplicationModel):
    """行動しない意思を表すapplication入力."""

    type: Literal["pass"]


PlayerActionInput = Annotated[
    SpeechActionInput | VoteActionInput | UseAbilityActionInput | PassActionInput,
    Field(discriminator="type"),
]


class PlayerActionCommand(ApplicationModel):
    """Manual playerの型付きactionを送信するcommandを表す."""

    game_id: str | UUID
    player_id: str
    action: PlayerActionInput
    trusted_user_id: str | None = None
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
