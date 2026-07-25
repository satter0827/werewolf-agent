"""Small object-oriented facade for game operations."""

from __future__ import annotations

from dataclasses import dataclass

import werewolf_agent.application.handlers as handlers
from werewolf_agent.application.definitions import (
    CustomCharacterDefinition,
    CustomRoleDefinition,
    LocalRulesDefinition,
)
from werewolf_agent.application.models import (
    AdvanceGameCommand,
    AdvanceGameResult,
    ApplicationContext,
    CreateGameCommand,
    GameListResult,
    GameResult,
    GameRevealResult,
    GameTimelineResult,
    GetGameQuery,
    GetGameRevealQuery,
    GetPlayerObservationQuery,
    ListGamesQuery,
    ListTimelineQuery,
    PlayerActionCommand,
    PlayerActionResult,
    PlayerObservationResult,
    ReplayVerificationResult,
)
from werewolf_agent.application.replay import verify_replay
from werewolf_agent.contracts import GameStatus
from werewolf_agent.contracts.schemas import CreateGameRequest, PlayerActionRequest


@dataclass(frozen=True)
class Actor:
    """Verified caller identity supplied by an outer security boundary."""

    user_id: str
    is_anonymous: bool = False
    is_admin: bool = False


class GameApplication:
    """Stateless facade exposing the complete Python game workflow."""

    def __init__(self, dependencies: ApplicationContext) -> None:
        """Create an application facade from validated dependencies."""
        self._dependencies = dependencies

    def create(
        self,
        input: CreateGameRequest,
    ) -> GameResult:
        """Create one game."""
        config = self._dependencies.config
        command = CreateGameCommand(
            seed=input.seed,
            role_counts=input.role_counts,
            manual_player_id=input.manual_player_id,
            rules=(
                LocalRulesDefinition.model_validate(input.rules.model_dump(mode="json"))
                if input.rules is not None
                else self._dependencies.game_definitions.rules.local_rules
            ),
            scenario_id=input.scenario_id,
            setup_preset_id=input.setup_preset_id,
            agent_strategy_id=input.agent_strategy_id or config.default_agent_strategy_id,
            narration_mode=input.narration_mode or config.default_narration_mode,
            character_assignments=input.character_assignments,
            custom_roles=[
                CustomRoleDefinition.model_validate(role.model_dump(mode="json"))
                for role in input.custom_roles
            ],
            custom_characters=[
                CustomCharacterDefinition.model_validate(character.model_dump(mode="json"))
                for character in input.custom_characters
            ],
            llm_mode=self._dependencies.create_llm_mode,
        )
        return handlers.create_game(command, dependencies=self._dependencies)

    def get(self, game_id: str, actor: Actor) -> GameResult:
        """Return one public game visible to the verified actor."""
        del actor
        return handlers.get_game(GetGameQuery(game_id=game_id), dependencies=self._dependencies)

    def list(
        self,
        actor: Actor,
        *,
        status: GameStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> GameListResult:
        """Return one page of games visible to the verified actor."""
        del actor
        return handlers.list_games(
            ListGamesQuery(status=status, limit=limit, offset=offset),
            dependencies=self._dependencies,
        )

    def submit_action(
        self,
        game_id: str,
        actor: Actor,
        action: PlayerActionRequest,
        expected_version: int,
        *,
        player_id: str,
    ) -> PlayerActionResult:
        """Submit a player action using server-verified identity and version."""
        command = PlayerActionCommand(
            game_id=game_id,
            player_id=player_id,
            trusted_user_id=actor.user_id,
            expected_version=expected_version,
            **action.model_dump(mode="python"),
        )
        return handlers.submit_player_action(command, dependencies=self._dependencies)

    def advance(
        self,
        game_id: str,
        actor: Actor,
        expected_version: int,
    ) -> AdvanceGameResult:
        """Advance one game from the expected public version."""
        del actor
        return handlers.advance_game(
            AdvanceGameCommand(game_id=game_id, expected_version=expected_version),
            dependencies=self._dependencies,
        )

    def timeline(
        self,
        game_id: str,
        actor: Actor,
        cursor: int = 0,
        *,
        limit: int | None = None,
    ) -> GameTimelineResult:
        """Return public timeline items after a cursor."""
        del actor
        return handlers.list_timeline(
            ListTimelineQuery(game_id=game_id, after=cursor, limit=limit),
            dependencies=self._dependencies,
        )

    def observation(
        self,
        game_id: str,
        actor: Actor,
        player_id: str,
    ) -> PlayerObservationResult:
        """Return the authenticated player's private observation."""
        return handlers.get_player_observation(
            GetPlayerObservationQuery(
                game_id=game_id,
                player_id=player_id,
                trusted_user_id=actor.user_id,
            ),
            dependencies=self._dependencies,
        )

    def reveal(self, game_id: str, admin: Actor) -> GameRevealResult:
        """Return complete state after the API has verified administrator access."""
        if not admin.is_admin:
            raise PermissionError("Administrator access is required.")
        return handlers.get_game_reveal(
            GetGameRevealQuery(game_id=game_id),
            dependencies=self._dependencies,
        )

    def verify_replay(self, game_id: str, admin: Actor) -> ReplayVerificationResult:
        """Verify persisted replay checksums without returning private payloads."""
        if not admin.is_admin:
            raise PermissionError("Administrator access is required.")
        repository = self._dependencies.repository
        if not hasattr(repository, "replay_records"):
            raise RuntimeError("The configured repository does not support replay verification.")
        return verify_replay(game_id, repository)  # type: ignore[arg-type]
