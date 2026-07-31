"""公開application facadeの例外境界を定義する."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from werewolf_agent.application.errors import (
    AppError,
    ErrorCode,
    GameNotFoundError,
    InternalError,
    InvalidGameIdError,
    ResourceNotFoundError,
)

_Result = TypeVar("_Result")


def public_result(operation: Callable[[], _Result]) -> _Result:
    """内部例外を公開application契約へ正規化する."""
    try:
        return operation()
    except AppError:
        raise
    except GameNotFoundError as exc:
        raise ResourceNotFoundError("指定したゲームが見つかりません。") from exc
    except PermissionError as exc:
        raise AppError(
            "この操作を実行する権限がありません。",
            code=ErrorCode.AUTHORIZATION_FAILED,
        ) from exc
    except InvalidGameIdError:
        raise
    except Exception as exc:
        raise InternalError() from exc


__all__: list[str] = []
