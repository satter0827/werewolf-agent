"""非同期command受付とaccess検査のapplication portを定義する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

OperationStatus = Literal["queued", "running", "succeeded", "failed"]


@dataclass(frozen=True)
class QueuedOperation:
    """許可された非同期operationの状態を表す。"""

    operation_id: str
    operation_type: str
    status: OperationStatus
    owner_user_id: str
    game_id: str | None
    expected_version: int | None
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class OperationQueue(Protocol):
    """Command受付が使用するqueue portを定義する。"""

    def enqueue(
        self,
        *,
        operation_type: str,
        owner_user_id: str,
        idempotency_key: str,
        request_payload: dict[str, Any],
        llm_mode: str | None,
        game_id: str | None = None,
        player_id: str | None = None,
        expected_version: int | None = None,
    ) -> QueuedOperation:
        """冪等なoperationを作成または取得して返す。

        llm_modeはゲーム作成時だけ渡す。既存ゲームを対象とするcommandでは、adapterが
        保存済みmodeを解決する。
        """

    def get(self, operation_id: str, *, owner_user_id: str) -> QueuedOperation | None:
        """呼出元が所有するoperationを返す。"""


class AccessPolicy(Protocol):
    """Request単位のゲーム認可portを定義する。"""

    def require_game_access(self, game_id: str, *, user_id: str) -> None:
        """Owner、player、observer、administratorのいずれかの権限を要求する。"""

    def require_player_access(self, game_id: str, player_id: str, *, user_id: str) -> None:
        """一つのplayer seatに対する所有権を要求する。"""


__all__ = ["AccessPolicy", "OperationQueue", "OperationStatus", "QueuedOperation"]
