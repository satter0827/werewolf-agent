"""外部serviceを必要としないapplication repository実装を提供する."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol, cast
from uuid import UUID, uuid4

from werewolf_agent.application.errors import AppError, ErrorCode, GameNotFoundError, GamePhaseError
from werewolf_agent.application.messages import MESSAGE_ADVANCE_JOB_STATE_CHANGED
from werewolf_agent.application.models import (
    GameEventCreate,
    GameRecordCreate,
    GameRecordUpdate,
    StoredGame,
    StoredGameEvent,
    StoredGameSummary,
    StoredGameTurn,
)
from werewolf_agent.application.ports import GameRepository, SetupRepository, Transaction
from werewolf_agent.application.setup_records import SavedSetupRevision, SavedSetupSummary
from werewolf_agent.application.types import GAME_STATUS_COMPLETED, GameStatus
from werewolf_agent.setup import GameSetupDocument


class Clock(Protocol):
    """Repositoryへ現在時刻を注入する契約."""

    def __call__(self) -> datetime:
        """Timezoneを持つ現在時刻を返す."""
        ...


class InMemoryGameRepository(GameRepository):
    """一つのprocess内で明示的に状態を所有するgame repository."""

    def __init__(self, *, owner_user_id: str, clock: Clock | None = None) -> None:
        """一つのownerに固定した空のrepositoryを作成する."""
        self._owner_user_id = owner_user_id
        self._clock = clock if clock is not None else _utc_now
        self._games: dict[UUID, StoredGame] = {}
        self._events: dict[UUID, list[StoredGameEvent]] = {}
        self._turns: dict[UUID, list[StoredGameTurn]] = {}
        self._lock = RLock()

    def transaction(self) -> Transaction:
        """Applicationの一更新単位を直列化し、失敗時に破棄する."""
        return cast(Transaction, self._transaction())

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        """現在の永続状態を保存し、例外時に更新単位全体を戻す."""
        with self._lock:
            snapshot = deepcopy((self._games, self._events, self._turns))
            try:
                yield
            except BaseException:
                self._games, self._events, self._turns = snapshot
                raise

    def create(self, game: GameRecordCreate) -> StoredGame:
        """新しいゲームsnapshotを保存する."""
        with self._lock:
            if game.id in self._games:
                raise ValueError(f"Game already exists: {game.id}")
            now = self._now()
            stored = StoredGame(
                **game.model_dump(mode="python"),
                created_at=now,
                updated_at=now,
            )
            self._games[game.id] = stored.model_copy(deep=True)
            self._events[game.id] = []
            self._turns[game.id] = []
            return stored.model_copy(deep=True)

    def get(self, game_id: UUID) -> StoredGame | None:
        """ゲームsnapshotが存在する場合にcopyを返す."""
        with self._lock:
            game = self._games.get(game_id)
            return None if game is None else game.model_copy(deep=True)

    def get_for_update(self, game_id: UUID) -> StoredGame | None:
        """現在のsnapshotを返し、競合は`save`のversion検証で拒否する."""
        return self.get(game_id)

    def list_game_summaries(
        self,
        *,
        user_id: str,
        status: GameStatus | None,
        limit: int,
        offset: int,
    ) -> list[StoredGameSummary]:
        """Ownerのゲーム概要を更新時刻の降順で返す."""
        if user_id != self._owner_user_id:
            return []
        with self._lock:
            summaries = [
                self._summary(game)
                for game in self._games.values()
                if status is None or game.status == status
            ]
            summaries.sort(
                key=lambda value: (value.updated_at, value.created_at),
                reverse=True,
            )
            return [item.model_copy(deep=True) for item in summaries[offset : offset + limit]]

    def save(self, update: GameRecordUpdate) -> StoredGame:
        """直前versionに続くゲームsnapshotを保存する."""
        with self._lock:
            current = self._games.get(update.id)
            if current is None:
                raise GameNotFoundError(f"Game not found: {update.id}")
            if update.version != current.version + 1:
                raise GamePhaseError(MESSAGE_ADVANCE_JOB_STATE_CHANGED)
            stored = StoredGame(
                id=current.id,
                status=update.status,
                phase=update.phase,
                day=update.day,
                seed=current.seed,
                config=current.config,
                public_state=update.public_state,
                private_state=update.private_state,
                pending_actions=update.pending_actions,
                version=update.version,
                created_at=current.created_at,
                updated_at=self._now(),
            )
            self._games[update.id] = stored.model_copy(deep=True)
            return stored.model_copy(deep=True)

    def append_events(
        self,
        game_id: UUID,
        events: Sequence[GameEventCreate],
    ) -> list[StoredGameEvent]:
        """Eventへ連番を付け、公開eventをtimelineへ投影する."""
        with self._lock:
            game = self._require_game(game_id)
            stream = self._events[game_id]
            turns = self._turns[game_id]
            stored_events: list[StoredGameEvent] = []
            for event in events:
                stored = StoredGameEvent(
                    sequence=len(stream) + 1,
                    event_id=uuid4(),
                    occurred_at=self._now(),
                    **event.model_dump(mode="python"),
                )
                stream.append(stored.model_copy(deep=True))
                stored_events.append(stored)
                if stored.visibility == "public":
                    turns.append(
                        StoredGameTurn(
                            sequence=len(turns) + 1,
                            event_sequence=stored.sequence,
                            version=game.version,
                            phase=stored.phase,
                            day=stored.day,
                            actor_id=stored.actor_id,
                            event_type=stored.event_type,
                            payload=stored.payload,
                            occurred_at=stored.occurred_at,
                        )
                    )
            return [event.model_copy(deep=True) for event in stored_events]

    def latest_public_turn_sequence(self, game_id: UUID) -> int:
        """最新の公開timeline sequenceを返す."""
        with self._lock:
            self._require_game(game_id)
            return len(self._turns[game_id])

    def list_public_turns(
        self,
        game_id: UUID,
        *,
        after: int,
        limit: int,
    ) -> list[StoredGameTurn]:
        """Cursorより後の公開timelineをsequence順で返す."""
        with self._lock:
            self._require_game(game_id)
            values = [turn for turn in self._turns[game_id] if turn.sequence > after]
            return [turn.model_copy(deep=True) for turn in values[:limit]]

    def _require_game(self, game_id: UUID) -> StoredGame:
        game = self._games.get(game_id)
        if game is None:
            raise GameNotFoundError(f"Game not found: {game_id}")
        return game

    def _summary(self, game: StoredGame) -> StoredGameSummary:
        public_state = game.public_state
        state_summary = public_state.get("summary")
        summary = state_summary if isinstance(state_summary, dict) else {}
        return StoredGameSummary(
            game_id=game.id,
            status=game.status,
            phase=game.phase,
            day=game.day,
            version=game.version,
            scenario_id=_optional_text(public_state.get("scenario_id")),
            scenario_name=_optional_text(public_state.get("scenario_name")),
            theme=_optional_object(public_state.get("theme")),
            player_count=len(public_state.get("players") or []),
            alive_count=int(summary.get("alive_count") or 0),
            winner=public_state.get("winner"),
            step_count=max(game.version - 1, 0),
            turn_count=len(self._turns[game.id]),
            created_at=game.created_at,
            updated_at=game.updated_at,
            completed_at=game.updated_at if game.status == GAME_STATUS_COMPLETED else None,
        )

    def _now(self) -> datetime:
        value = self._clock()
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class InMemorySetupRepository(SetupRepository):
    """所有者分離とimmutable revisionをprocess内で実現するrepository."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        """空のsetup repositoryを作成する."""
        self._clock = clock if clock is not None else _utc_now
        self._setups: dict[str, tuple[str, str, list[SavedSetupRevision]]] = {}
        self._lock = RLock()

    def create(
        self,
        *,
        owner_user_id: str,
        display_name: str,
        document: GameSetupDocument,
        setup_checksum: str,
        mechanics_checksum: str,
    ) -> SavedSetupRevision:
        """Ownerへ紐づく最初のsetup revisionを作成する."""
        with self._lock:
            setup_id = str(uuid4())
            revision = SavedSetupRevision(
                setup_id=setup_id,
                display_name=display_name,
                revision=1,
                document=document,
                setup_checksum=setup_checksum,
                mechanics_checksum=mechanics_checksum,
                created_at=self._now(),
            )
            self._setups[setup_id] = (owner_user_id, display_name, [revision])
            return revision.model_copy()

    def list_setups(self, *, owner_user_id: str) -> list[SavedSetupSummary]:
        """Ownerが所有するsetup概要を更新時刻の降順で返す."""
        with self._lock:
            values = [
                SavedSetupSummary(
                    setup_id=setup_id,
                    display_name=display_name,
                    latest_revision=revisions[-1].revision,
                    created_at=revisions[0].created_at,
                    updated_at=revisions[-1].created_at,
                )
                for setup_id, (owner, display_name, revisions) in self._setups.items()
                if owner == owner_user_id
            ]
            values.sort(key=lambda value: (-value.updated_at.timestamp(), value.setup_id))
            return [value.model_copy() for value in values]

    def get(
        self,
        setup_id: str,
        *,
        owner_user_id: str,
        revision: int | None = None,
    ) -> SavedSetupRevision | None:
        """Ownerが所有する指定revisionまたは最新版を返す."""
        with self._lock:
            record = self._setups.get(setup_id)
            if record is None or record[0] != owner_user_id:
                return None
            revisions = record[2]
            result = (
                revisions[-1]
                if revision is None
                else next(
                    (item for item in revisions if item.revision == revision),
                    None,
                )
            )
            return None if result is None else result.model_copy()

    def list_revisions(
        self,
        setup_id: str,
        *,
        owner_user_id: str,
    ) -> list[SavedSetupRevision]:
        """Ownerが所有するrevisionを新しい順で返す."""
        with self._lock:
            record = self._setups.get(setup_id)
            if record is None or record[0] != owner_user_id:
                return []
            return [item.model_copy() for item in reversed(record[2])]

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
        """期待する最新版が一致する場合だけ次のrevisionを追加する."""
        with self._lock:
            record = self._setups.get(setup_id)
            if record is None or record[0] != owner_user_id:
                raise AppError(
                    "指定したゲーム設定が見つかりません。",
                    code=ErrorCode.RESOURCE_NOT_FOUND,
                )
            latest = record[2][-1]
            if latest.revision != expected_revision:
                raise AppError(
                    "別の版が先に保存されています。最新の設定を読み直してください。",
                    code=ErrorCode.SETUP_REVISION_CONFLICT,
                    context={
                        "expected_revision": expected_revision,
                        "latest_revision": latest.revision,
                    },
                )
            revision = SavedSetupRevision(
                setup_id=setup_id,
                display_name=record[1],
                revision=latest.revision + 1,
                document=document,
                setup_checksum=setup_checksum,
                mechanics_checksum=mechanics_checksum,
                created_at=self._now(),
            )
            record[2].append(revision)
            return revision.model_copy()

    def _now(self) -> datetime:
        value = self._clock()
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_object(value: object) -> dict[str, object] | None:
    return dict(value) if isinstance(value, dict) else None


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = ["Clock", "InMemoryGameRepository", "InMemorySetupRepository"]
