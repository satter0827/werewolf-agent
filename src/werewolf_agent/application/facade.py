"""Small object-oriented facade for game operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

import werewolf_agent.application.handlers as handlers
from werewolf_agent.application.errors import (
    AppError,
    ConfigError,
    ErrorCode,
    GameNotFoundError,
    ResourceNotFoundError,
)
from werewolf_agent.application.models import (
    AdvanceGameCommand,
    AdvanceGameResult,
    ApplicationContext,
    ComputedAdvanceGame,
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
    PreparedAdvanceGame,
    ReplayVerificationResult,
)
from werewolf_agent.application.operations import AccessPolicy, OperationQueue, QueuedOperation
from werewolf_agent.application.replay import verify_replay
from werewolf_agent.application.types import GameStatus

_Result = TypeVar("_Result")


@dataclass(frozen=True)
class Actor:
    """Verified caller identity supplied by an outer security boundary."""

    user_id: str
    is_anonymous: bool = False
    is_admin: bool = False

    def __post_init__(self) -> None:
        """Normalize and require a stable external subject identifier."""
        user_id = self.user_id.strip()
        if not user_id:
            raise ValueError("Actor user_id must not be blank.")
        object.__setattr__(self, "user_id", user_id)


class GameApplication:
    """Stateless facade exposing the complete Python game workflow."""

    def __init__(
        self,
        dependencies: ApplicationContext,
        *,
        access_policy: AccessPolicy | None = None,
        operation_queue: OperationQueue | None = None,
    ) -> None:
        """Create an application facade from validated dependencies."""
        self._dependencies = dependencies
        self._access_policy = access_policy
        self._operation_queue = operation_queue

    def create(
        self,
        command: CreateGameCommand,
    ) -> GameResult:
        """Create one game."""
        trusted = command.model_copy(update={"llm_mode": self._dependencies.create_llm_mode})
        return handlers.create_game(trusted, dependencies=self._dependencies)

    def get(self, game_id: str, actor: Actor) -> GameResult:
        """Return one public game visible to the verified actor."""
        self._require_game_access(game_id, actor)
        return _resource_result(
            lambda: handlers.get_game(
                GetGameQuery(game_id=game_id), dependencies=self._dependencies
            )
        )

    def list(
        self,
        actor: Actor,
        *,
        status: GameStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> GameListResult:
        """Return one page of games visible to the verified actor."""
        return handlers.list_games(
            ListGamesQuery(
                trusted_user_id=actor.user_id,
                status=status,
                limit=limit,
                offset=offset,
            ),
            dependencies=self._dependencies,
        )

    def submit_action(
        self,
        actor: Actor,
        command: PlayerActionCommand,
    ) -> PlayerActionResult:
        """Submit a player action using server-verified identity and version."""
        self._require_player_access(str(command.game_id), command.player_id, actor)
        trusted = command.model_copy(update={"trusted_user_id": actor.user_id})
        return _resource_result(
            lambda: handlers.submit_player_action(trusted, dependencies=self._dependencies)
        )

    def advance(
        self,
        game_id: str,
        actor: Actor,
        expected_version: int,
    ) -> AdvanceGameResult:
        """Advance one game from the expected public version."""
        self._require_game_access(game_id, actor)
        return _resource_result(
            lambda: handlers.advance_game(
                AdvanceGameCommand(game_id=game_id, expected_version=expected_version),
                dependencies=self._dependencies,
            )
        )

    def prepare_advance(
        self,
        game_id: str,
        actor: Actor,
        expected_version: int,
    ) -> PreparedAdvanceGame:
        """Authorize and prepare a versioned advance for an external agent runtime."""
        self._require_game_access(game_id, actor)
        return _resource_result(
            lambda: handlers.prepare_advance_game(
                AdvanceGameCommand(game_id=game_id, expected_version=expected_version),
                dependencies=self._dependencies,
            )
        )

    def compute_advance(
        self,
        prepared: PreparedAdvanceGame,
    ) -> ComputedAdvanceGame:
        """Apply validated agent decisions without performing I/O."""
        return handlers.compute_prepared_advance(prepared)

    def commit_advance(
        self,
        actor: Actor,
        computed: ComputedAdvanceGame,
    ) -> AdvanceGameResult:
        """Authorize and commit a previously computed advance."""
        self._require_game_access(computed.game_id, actor)
        return _resource_result(
            lambda: handlers.commit_prepared_advance(computed, dependencies=self._dependencies)
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
        self._require_game_access(game_id, actor)
        return _resource_result(
            lambda: handlers.list_timeline(
                ListTimelineQuery(game_id=game_id, after=cursor, limit=limit),
                dependencies=self._dependencies,
            )
        )

    def observation(
        self,
        game_id: str,
        actor: Actor,
        player_id: str,
    ) -> PlayerObservationResult:
        """Return the authenticated player's private observation."""
        self._require_player_access(game_id, player_id, actor)
        return _resource_result(
            lambda: handlers.get_player_observation(
                GetPlayerObservationQuery(
                    game_id=game_id,
                    player_id=player_id,
                    trusted_user_id=actor.user_id,
                ),
                dependencies=self._dependencies,
            )
        )

    def reveal(self, game_id: str, admin: Actor) -> GameRevealResult:
        """Return complete state after the API has verified administrator access."""
        if not admin.is_admin:
            raise AppError(
                "管理者権限が必要です。",
                code=ErrorCode.AUTHORIZATION_FAILED,
            )
        return _resource_result(
            lambda: handlers.get_game_reveal(
                GetGameRevealQuery(game_id=game_id),
                dependencies=self._dependencies,
            )
        )

    def verify_replay(self, game_id: str, admin: Actor) -> ReplayVerificationResult:
        """Verify persisted replay checksums without returning private payloads."""
        if not admin.is_admin:
            raise AppError(
                "管理者権限が必要です。",
                code=ErrorCode.AUTHORIZATION_FAILED,
            )
        repository = self._dependencies.repository
        if not hasattr(repository, "replay_records"):
            raise ConfigError("repositoryにreplay検証機能が構成されていません。")
        return verify_replay(game_id, repository)  # type: ignore[arg-type]

    def enqueue_create(
        self,
        actor: Actor,
        *,
        idempotency_key: str,
        request_payload: dict[str, object],
        llm_mode: str,
    ) -> QueuedOperation:
        """Queue one game creation command for the verified actor."""
        return self._queue().enqueue(
            operation_type="create_game",
            owner_user_id=actor.user_id,
            idempotency_key=idempotency_key,
            request_payload=request_payload,
            llm_mode=llm_mode,
        )

    def enqueue_action(
        self,
        game_id: str,
        actor: Actor,
        *,
        player_id: str,
        expected_version: int,
        idempotency_key: str,
        request_payload: dict[str, object],
    ) -> QueuedOperation:
        """Authorize and queue one player action."""
        self._require_player_access(game_id, player_id, actor)
        return self._queue().enqueue(
            operation_type="submit_action",
            owner_user_id=actor.user_id,
            idempotency_key=idempotency_key,
            request_payload=request_payload,
            llm_mode=None,
            game_id=game_id,
            player_id=player_id,
            expected_version=expected_version,
        )

    def enqueue_advance(
        self,
        game_id: str,
        actor: Actor,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> QueuedOperation:
        """Authorize and queue one game advance."""
        self._require_game_access(game_id, actor)
        return self._queue().enqueue(
            operation_type="advance_game",
            owner_user_id=actor.user_id,
            idempotency_key=idempotency_key,
            request_payload={},
            llm_mode=None,
            game_id=game_id,
            expected_version=expected_version,
        )

    def operation(self, operation_id: str, actor: Actor) -> QueuedOperation | None:
        """Return an asynchronous operation owned by the verified actor."""
        return self._queue().get(operation_id, owner_user_id=actor.user_id)

    def _queue(self) -> OperationQueue:
        if self._operation_queue is None:
            raise ConfigError("operation queueが構成されていません。")
        return self._operation_queue

    def _require_game_access(self, game_id: str, actor: Actor) -> None:
        if self._access_policy is None:
            raise ConfigError("access policyが構成されていません。")
        try:
            self._access_policy.require_game_access(game_id, user_id=actor.user_id)
        except PermissionError as exc:
            raise AppError(
                "このゲームを操作する権限がありません。",
                code=ErrorCode.AUTHORIZATION_FAILED,
            ) from exc

    def _require_player_access(self, game_id: str, player_id: str, actor: Actor) -> None:
        if self._access_policy is None:
            raise ConfigError("access policyが構成されていません。")
        try:
            self._access_policy.require_player_access(game_id, player_id, user_id=actor.user_id)
        except PermissionError as exc:
            raise AppError(
                "このプレイヤーを操作する権限がありません。",
                code=ErrorCode.AUTHORIZATION_FAILED,
            ) from exc


def _resource_result(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except GameNotFoundError as exc:
        raise ResourceNotFoundError("指定したゲームが見つかりません。") from exc
