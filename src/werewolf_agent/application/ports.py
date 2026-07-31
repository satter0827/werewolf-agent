"""外側のadapterが実装するportを定義する."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from werewolf_agent.application.models import (
    GameEventCreate,
    GameRecordCreate,
    GameRecordUpdate,
    StoredGame,
    StoredGameEvent,
    StoredGameSummary,
    StoredGameTurn,
)
from werewolf_agent.application.setup_records import SavedSetupRevision, SavedSetupSummary
from werewolf_agent.application.types import GameStatus
from werewolf_agent.setup import GameSetupDocument


class GameRepository(Protocol):
    """Statelessなゲーム処理が必要とする永続化操作を定義する."""

    def create(self, game: GameRecordCreate) -> StoredGame:
        """新しいゲームを保存して結果を返す.

        Args:
            game: 新しいゲームの完全な永続化payload。

        Returns:
            Repositoryがtimestampを付与した保存済みゲーム。

        """

    def get(self, game_id: UUID) -> StoredGame | None:
        """ゲームが存在する場合に返す.

        Args:
            game_id: ゲームID。

        Returns:
            保存済みゲーム。不在の場合は`None`。

        """

    def get_for_update(self, game_id: UUID) -> StoredGame | None:
        """ゲームが存在する場合に更新lockを取得して返す.

        Args:
            game_id: ゲームID。

        Returns:
            保存済みゲーム。不在の場合は`None`。

        """

    def list_game_summaries(
        self,
        *,
        user_id: str,
        status: GameStatus | None,
        limit: int,
        offset: int,
    ) -> list[StoredGameSummary]:
        """ゲーム概要の一pageを返す.

        Args:
            user_id: 参加ゲームを閲覧する検証済み利用者ID。
            status: 任意の公開ゲームstatus filter。
            limit: 返す概要の最大数。
            offset: Paginationの開始位置。

        Returns:
            表示順に並んだ公開ゲーム概要。

        """

    def save(self, update: GameRecordUpdate) -> StoredGame:
        """一つのゲームの可変fieldを保存して返す.

        Args:
            update: Applicationの一step後に更新するゲームfield。

        Returns:
            更新後の保存済みゲーム。

        """

    def append_events(
        self,
        game_id: UUID,
        events: Sequence[GameEventCreate],
    ) -> list[StoredGameEvent]:
        """Eventを追加し、stream sequence番号を付与して返す.

        Args:
            game_id: Eventを所有するゲームID。
            events: Domainから導出した保存対象event。

        Returns:
            Sequence番号を付与した保存済みevent。

        """

    def latest_public_turn_sequence(self, game_id: UUID) -> int:
        """一つのゲームの最新公開timeline sequenceを返す.

        Args:
            game_id: Timelineを所有するゲームID。

        Returns:
            最新の公開timeline sequence。Timelineが空の場合は`0`。

        """

    def list_public_turns(
        self,
        game_id: UUID,
        *,
        after: int,
        limit: int,
    ) -> list[StoredGameTurn]:
        """Sequence cursorより後の公開turn記録を返す.

        Args:
            game_id: Timelineを所有するゲームID。
            after: 対象に含めないturn sequence cursor。
            limit: 返すturn記録の最大数。

        Returns:
            Sequence順に並んだ公開turn記録。

        """


class SetupRepository(Protocol):
    """利用者所有のimmutable setup revisionを扱う永続化操作を定義する."""

    def create(
        self,
        *,
        owner_user_id: str,
        display_name: str,
        document: GameSetupDocument,
        setup_checksum: str,
        mechanics_checksum: str,
    ) -> SavedSetupRevision:
        """所有setupと最初のimmutable revisionを作成して返す."""
        ...

    def list_setups(self, *, owner_user_id: str) -> list[SavedSetupSummary]:
        """指定した利用者が所有するsetup概要だけを返す."""
        ...

    def get(
        self,
        setup_id: str,
        *,
        owner_user_id: str,
        revision: int | None = None,
    ) -> SavedSetupRevision | None:
        """他者のrowを開示せず、所有revisionまたは`None`を返す."""
        ...

    def list_revisions(
        self,
        setup_id: str,
        *,
        owner_user_id: str,
    ) -> list[SavedSetupRevision]:
        """所有する一つのsetupのimmutable revisionを返す."""
        ...

    def add_revision(
        self,
        setup_id: str,
        *,
        owner_user_id: str,
        expected_revision: int,
        document: GameSetupDocument,
        setup_checksum: str,
        mechanics_checksum: str,
    ) -> SavedSetupRevision:
        """楽観的並行性検証後にrevisionを追加して返す."""
        ...
