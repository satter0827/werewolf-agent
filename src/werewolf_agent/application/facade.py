"""ゲーム操作をまとめるobject-oriented facadeを定義する。"""

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
    """外側のsecurity境界が検証した呼出主体を表す。"""

    user_id: str
    is_anonymous: bool = False
    is_admin: bool = False

    def __post_init__(self) -> None:
        """安定した外部subject IDを正規化して必須とする。"""
        user_id = self.user_id.strip()
        if not user_id:
            raise ValueError("Actor user_id must not be blank.")
        object.__setattr__(self, "user_id", user_id)


class GameApplication:
    """完全なPythonゲーム手順を提供するstateless facadeを表す。"""

    def __init__(
        self,
        dependencies: ApplicationContext,
        *,
        access_policy: AccessPolicy | None = None,
        operation_queue: OperationQueue | None = None,
    ) -> None:
        """検証済み依存関係からapplication facadeを構築する。"""
        self._dependencies = dependencies
        self._access_policy = access_policy
        self._operation_queue = operation_queue

    def create(
        self,
        command: CreateGameCommand,
    ) -> GameResult:
        """一つのゲームを作成して現在状態を返す。"""
        trusted = command.model_copy(update={"llm_mode": self._dependencies.create_llm_mode})
        return handlers.create_game(trusted, dependencies=self._dependencies)

    def get(self, game_id: str, actor: Actor) -> GameResult:
        """検証済みactorが閲覧できる一つの公開ゲームを返す。"""
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
        """検証済みactorが閲覧できるゲームの一pageを返す。"""
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
        """Serverが検証したidentityとversionでplayer actionを送信する。"""
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
        """期待する公開versionからゲームを一step進めて結果を返す。"""
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
        """外部agent runtime向けにversion付き進行を認可して準備する。"""
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
        """I/Oを行わず、検証済みagent decisionを適用する。"""
        return handlers.compute_prepared_advance(prepared)

    def commit_advance(
        self,
        actor: Actor,
        computed: ComputedAdvanceGame,
    ) -> AdvanceGameResult:
        """計算済み進行を認可してcommitする。"""
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
        """Cursorより後の公開timeline itemを返す。"""
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
        """認証済みplayer本人のprivate observationを返す。"""
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
        """APIが管理者権限を検証した後に完全状態を返す。"""
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
        """Private payloadを返さず保存済みreplay checksumを検証する。"""
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
        """検証済みactorのゲーム作成commandをqueueへ登録する。"""
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
        """一つのplayer actionを認可してqueueへ登録する。"""
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
        """一つのゲーム進行を認可してqueueへ登録する。"""
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
        """検証済みactorが所有する非同期operationを返す。"""
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
