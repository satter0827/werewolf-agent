"""Public game use case DTOs and a small stateless facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from werewolf_agent.commons.shared.definitions import (
    CustomCharacterDefinition,
    CustomRoleDefinition,
    GameDefinitions,
    LlmDefinitions,
    LocalRulesDefinition,
)
from werewolf_agent.commons.shared.messages import MESSAGE_PLAYER_COUNT_AT_LEAST_ONE
from werewolf_agent.commons.shared.models import StrictModel
from werewolf_agent.commons.shared.validation import non_blank
from werewolf_agent.usecase.jobs.telemetry import NullTelemetrySink, TelemetrySink

if TYPE_CHECKING:
    from werewolf_agent.usecase.jobs.ports import GameRepository

GamePhase = Literal["night", "day_discussion", "voting", "finished"]
GameStatus = Literal["running", "completed"]
EventVisibility = Literal["public", "player_private", "debug"]
ActionTypeId = str
RoleId = str
Winner = Literal["villagers", "werewolves"]
RoleCount = Annotated[int, Field(ge=0)]
NarrationMode = Literal["none", "standard", "rich"]


@dataclass(frozen=True)
class LlmProviderConfig:
    """Use case settings for automated LangChain-backed players."""

    provider: str
    model: str
    base_url: str
    api_key: str = field(repr=False)
    timeout_seconds: float
    max_retries: int
    temperature: float

    def __post_init__(self) -> None:
        """Validate provider settings without importing interface settings."""
        provider = non_blank(self.provider, "llm provider").lower()
        model = non_blank(self.model, "llm model")
        base_url = self.base_url.strip()
        api_key = self.api_key.strip()
        if self.timeout_seconds <= 0:
            raise ValueError("llm timeout_seconds must be greater than 0")
        if self.max_retries < 0:
            raise ValueError("llm max_retries must be at least 0")
        if not 0 <= self.temperature <= 2:
            raise ValueError("llm temperature must be between 0 and 2")
        if provider == "lmstudio" and not base_url:
            raise ValueError("llm base_url is required for lmstudio provider")
        if provider == "openai" and not api_key:
            raise ValueError("OPENAI_API_KEY is required for openai provider")

        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "api_key", api_key)


@dataclass(frozen=True)
class GameUseCaseConfig:
    """Business settings used by stateless game jobs."""

    min_players: int
    max_players: int
    default_player_count: int
    supported_agent_type: str
    default_setup_id: str


@dataclass(frozen=True)
class GameUseCaseDependencies:
    """Externally supplied dependencies for game use cases."""

    repository: GameRepository
    game_definitions: GameDefinitions
    llm_definitions: LlmDefinitions
    config: GameUseCaseConfig
    llm_provider_config: LlmProviderConfig
    telemetry: TelemetrySink = field(default_factory=NullTelemetrySink)


class _UseCaseModel(StrictModel):
    """Base model for public use case DTOs."""


class CreateGameCommand(_UseCaseModel):
    """Command for creating one game."""

    seed: int | None = None
    scenario_id: str | None = None
    setup_preset_id: str | None = None
    narration_mode: NarrationMode = "standard"
    role_counts: dict[RoleId, RoleCount]
    rules: LocalRulesDefinition
    manual_player_id: str | None = None
    character_assignments: dict[str, str] = Field(default_factory=dict)
    custom_roles: list[CustomRoleDefinition] = Field(default_factory=list)
    custom_characters: list[CustomCharacterDefinition] = Field(default_factory=list)

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
        valid_player_ids = {f"player-{index}" for index in range(1, self.player_count + 1)}
        if self.manual_player_id is not None and self.manual_player_id not in valid_player_ids:
            raise ValueError("manual_player_id must match a generated player id")
        unknown_assignments = sorted(set(self.character_assignments) - valid_player_ids)
        if unknown_assignments:
            raise ValueError("character_assignments keys must match generated player ids")
        assigned_character_ids = list(self.character_assignments.values())
        if len(set(assigned_character_ids)) != len(assigned_character_ids):
            raise ValueError("character_assignments values must be unique")
        custom_role_ids = [definition.id for definition in self.custom_roles]
        if len(set(custom_role_ids)) != len(custom_role_ids):
            raise ValueError("custom role ids must be unique")
        custom_character_ids = [definition.id for definition in self.custom_characters]
        if len(set(custom_character_ids)) != len(custom_character_ids):
            raise ValueError("custom character ids must be unique")
        return self

    @property
    def player_count(self) -> int:
        """Return the player count derived from role counts."""
        return sum(self.role_counts.values())


class GetGameQuery(_UseCaseModel):
    """Query for loading one game."""

    game_id: str | UUID

    model_config = ConfigDict(extra="forbid", frozen=True)


class GetGameRevealQuery(_UseCaseModel):
    """Query for loading full observer-only game information."""

    game_id: str | UUID

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceGameCommand(_UseCaseModel):
    """Command for advancing one game by one business step."""

    game_id: str | UUID

    model_config = ConfigDict(extra="forbid", frozen=True)


class GetPlayerObservationQuery(_UseCaseModel):
    """Query for one player's private observation."""

    game_id: str | UUID
    player_id: str
    manual_token: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerActionCommand(_UseCaseModel):
    """Command for submitting one manual player action."""

    game_id: str | UUID
    player_id: str
    manual_token: str
    type: ActionTypeId
    target_id: str | None = None
    message: str | None = None
    reason: str = ""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ListGamesQuery(_UseCaseModel):
    """Query for listing public games."""

    status: GameStatus | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class ListTimelineQuery(_UseCaseModel):
    """Query for listing public timeline items after a sequence cursor."""

    game_id: str | UUID
    after: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=500)

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameSetupOptionsResult(_UseCaseModel):
    """Game setup metadata returned by use cases."""

    player_count: dict[str, int]
    roles: dict[RoleId, dict[str, Any]]
    default_role_counts: dict[RoleId, RoleCount]
    default_rules: LocalRulesDefinition
    default_scenario_id: str | None = None
    default_setup_preset_id: str | None = None
    default_narration_mode: NarrationMode = "standard"
    abilities: dict[str, dict[str, Any]] = Field(default_factory=dict)
    scenarios: dict[str, dict[str, Any]] = Field(default_factory=dict)
    setup_presets: dict[str, dict[str, Any]] = Field(default_factory=dict)
    characters: dict[str, dict[str, Any]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)


class ManualPlayerCredential(_UseCaseModel):
    """Plain manual-player credential returned only on game creation."""

    player_id: str
    token: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameResult(_UseCaseModel):
    """Current game state returned by use cases."""

    game_id: str
    state: dict[str, Any]
    manual_player: ManualPlayerCredential | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealPlayer(_UseCaseModel):
    """Full player state for the dedicated reveal boundary."""

    id: str
    name: str
    role: RoleId
    faction: str
    alive: bool
    status: str
    eliminated_day: int | None = None
    killed_night: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealAction(_UseCaseModel):
    """Pending action for the dedicated reveal boundary."""

    player_id: str
    type: ActionTypeId
    target_id: str | None = None
    message: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealInspection(_UseCaseModel):
    """Resolved inspection for the dedicated reveal boundary."""

    seer_id: str
    target_id: str
    target_role: RoleId
    target_faction: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealNight(_UseCaseModel):
    """Resolved night record for the dedicated reveal boundary."""

    day: int
    attacked_player_id: str | None = None
    protected_player_id: str | None = None
    killed_player_id: str | None = None
    inspections: list[GameRevealInspection] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealVote(_UseCaseModel):
    """Resolved vote record for the dedicated reveal boundary."""

    day: int
    votes: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    tied_player_ids: list[str] = Field(default_factory=list)
    missing_voter_ids: list[str] = Field(default_factory=list)
    eliminated_player_id: str | None = None
    tie_break_policy: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRevealResult(_UseCaseModel):
    """Full table information for local observer/demo clients."""

    game_id: str
    status: GameStatus
    phase: GamePhase
    day: int
    version: int
    seed: int | None
    scenario_id: str | None = None
    scenario_name: str | None = None
    narration_mode: NarrationMode = "standard"
    role_counts: dict[RoleId, RoleCount]
    rules: LocalRulesDefinition
    players: list[GameRevealPlayer]
    alive_player_ids: list[str]
    eliminated_player_ids: list[str]
    winner: Winner | None = None
    pending_votes: list[GameRevealAction] = Field(default_factory=list)
    pending_night_actions: list[GameRevealAction] = Field(default_factory=list)
    votes: list[GameRevealVote] = Field(default_factory=list)
    nights: list[GameRevealNight] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerObservationResult(_UseCaseModel):
    """Private observation returned to an authenticated player."""

    game_id: str
    player_id: str
    observation: dict[str, Any]

    model_config = ConfigDict(extra="forbid", frozen=True)


class PlayerActionResult(_UseCaseModel):
    """Result after accepting one manual player action."""

    game_id: str
    player_id: str
    state: dict[str, Any]
    timeline: list[dict[str, Any]]

    model_config = ConfigDict(extra="forbid", frozen=True)


class AdvanceGameResult(_UseCaseModel):
    """Result from advancing a game by one use case step."""

    game_id: str
    status: GameStatus
    state: dict[str, Any]
    timeline: list[dict[str, Any]]

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameTimelineResult(_UseCaseModel):
    """Page of public timeline items."""

    game_id: str
    items: list[dict[str, Any]]
    next_after: int

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameListResult(_UseCaseModel):
    """Page of public game summaries."""

    games: list[dict[str, Any]]
    next_offset: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicPlayerState(_UseCaseModel):
    """Internal public player state projected from domain state."""

    id: str
    name: str
    alive: bool
    status: str
    eliminated_day: int | None = None
    killed_night: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicGameState(_UseCaseModel):
    """Internal public game state projected from domain state."""

    game_id: str
    status: GameStatus
    phase: GamePhase
    day: int
    version: int
    seed: int | None
    scenario_id: str | None = None
    scenario_name: str | None = None
    narration_mode: NarrationMode = "standard"
    players: list[PublicPlayerState]
    alive_player_ids: list[str]
    eliminated_player_ids: list[str]
    winner: Winner | None = None
    summary: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicGameSummary(_UseCaseModel):
    """Public summary of a persisted game."""

    game_id: str
    status: GameStatus
    phase: GamePhase
    day: int
    version: int
    seed: int | None
    player_count: int
    alive_count: int
    winner: Winner | None = None
    step_count: int
    turn_count: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameTimelineItem(_UseCaseModel):
    """Public turn/event record optimized for external timelines."""

    sequence: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    version: int = Field(ge=1)
    phase: GamePhase | None = None
    day: int | None = None
    actor_id: str | None = None
    event_type: str
    narration: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameEventCreate(_UseCaseModel):
    """Sanitized event data to persist through an outer repository."""

    visibility: EventVisibility
    phase: GamePhase | None = None
    day: int | None = None
    actor_id: str | None = None
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)


class StoredGameTurn(_UseCaseModel):
    """Turn read-model record loaded from an outer persistence adapter."""

    sequence: int
    event_sequence: int
    version: int
    phase: GamePhase | None = None
    day: int | None = None
    actor_id: str | None = None
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


class StoredGameSummary(_UseCaseModel):
    """Game summary read model loaded from an outer persistence adapter."""

    game_id: UUID
    status: GameStatus
    phase: GamePhase
    day: int
    version: int
    seed: int | None
    player_count: int
    alive_count: int
    winner: Winner | None = None
    step_count: int
    turn_count: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRecordCreate(_UseCaseModel):
    """New game data to be persisted by an outer repository."""

    id: UUID
    status: GameStatus
    phase: GamePhase
    day: int
    seed: int | None
    config: dict[str, Any]
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    pending_actions: dict[str, Any] = Field(default_factory=dict)
    manual_token_hashes: dict[str, str] = Field(default_factory=dict)
    version: int

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameRecordUpdate(_UseCaseModel):
    """Persistable updates for an existing game."""

    id: UUID
    status: GameStatus
    phase: GamePhase
    day: int
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    pending_actions: dict[str, Any] = Field(default_factory=dict)
    version: int

    model_config = ConfigDict(extra="forbid", frozen=True)


class StoredGame(_UseCaseModel):
    """Game loaded from an outer persistence adapter."""

    id: UUID
    status: GameStatus
    phase: GamePhase
    day: int
    seed: int | None
    config: dict[str, Any]
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    pending_actions: dict[str, Any] = Field(default_factory=dict)
    manual_token_hashes: dict[str, str] = Field(default_factory=dict)
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


class StoredGameEvent(_UseCaseModel):
    """Event record loaded from an outer persistence adapter."""

    sequence: int
    event_id: UUID
    visibility: EventVisibility
    phase: GamePhase | None = None
    day: int | None = None
    actor_id: str | None = None
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)


class GameService:
    """Small facade over internal game workflows with injected dependencies."""

    def __init__(self, dependencies: GameUseCaseDependencies) -> None:
        """Store dependencies used by all game use case calls."""
        self._dependencies = dependencies

    @staticmethod
    def get_setup_options(
        config: GameUseCaseConfig,
        game_definitions: GameDefinitions,
        llm_definitions: LlmDefinitions,
    ) -> GameSetupOptionsResult:
        """Return business metadata for game setup."""
        from werewolf_agent.usecase.internal.setup_options import default_setup_options

        return default_setup_options(
            config,
            game_definitions,
            llm_definitions,
        )

    def create_game(self, command: CreateGameCommand) -> GameResult:
        """Create and persist one deterministic game."""
        from werewolf_agent.usecase.internal.games import create_game

        return create_game(command, dependencies=self._dependencies)

    def get_game(self, query: GetGameQuery) -> GameResult:
        """Return the current public state for one game."""
        from werewolf_agent.usecase.internal.games import get_game

        return get_game(query, dependencies=self._dependencies)

    def get_game_reveal(self, query: GetGameRevealQuery) -> GameRevealResult:
        """Return observer-only full game information."""
        from werewolf_agent.usecase.internal.games import get_game_reveal

        return get_game_reveal(query, dependencies=self._dependencies)

    def list_games(self, query: ListGamesQuery) -> GameListResult:
        """Return a page of public game summaries."""
        from werewolf_agent.usecase.internal.games import list_games

        return list_games(query, dependencies=self._dependencies)

    def advance_game(self, command: AdvanceGameCommand) -> AdvanceGameResult:
        """Advance one game by one business step."""
        from werewolf_agent.usecase.internal.games import advance_game

        return advance_game(command, dependencies=self._dependencies)

    def get_player_observation(
        self,
        query: GetPlayerObservationQuery,
    ) -> PlayerObservationResult:
        """Return one authenticated player's private observation."""
        from werewolf_agent.usecase.internal.games import get_player_observation

        return get_player_observation(query, dependencies=self._dependencies)

    def submit_player_action(self, command: PlayerActionCommand) -> PlayerActionResult:
        """Submit one authenticated manual player action."""
        from werewolf_agent.usecase.internal.games import submit_player_action

        return submit_player_action(command, dependencies=self._dependencies)

    def list_timeline(self, query: ListTimelineQuery) -> GameTimelineResult:
        """Return public timeline items after a sequence number."""
        from werewolf_agent.usecase.internal.games import list_timeline

        return list_timeline(query, dependencies=self._dependencies)
