"""Application ports for asynchronous command delivery and access checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

OperationStatus = Literal["queued", "running", "succeeded", "failed"]


@dataclass(frozen=True)
class QueuedOperation:
    """Allowlisted asynchronous operation state."""

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
    """Queue port used by command-oriented HTTP endpoints."""

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
        """Create or return one idempotent operation.

        ``llm_mode`` is supplied only while creating a game. Adapters resolve
        the persisted mode for commands targeting an existing game.
        """

    def get(self, operation_id: str, *, owner_user_id: str) -> QueuedOperation | None:
        """Return one operation owned by the caller."""


class AccessPolicy(Protocol):
    """Request-scoped game authorization port."""

    def require_game_access(self, game_id: str, *, user_id: str) -> None:
        """Require owner, player, observer, or administrator access."""

    def require_player_access(self, game_id: str, player_id: str, *, user_id: str) -> None:
        """Require ownership of one player seat."""


__all__ = ["AccessPolicy", "OperationQueue", "OperationStatus", "QueuedOperation"]
