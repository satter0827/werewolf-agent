"""Application bridge errors raised before HTTP translation."""

from __future__ import annotations

from werewolf_agent.commons.shared.codes import ErrorCode
from werewolf_agent.contracts import AppError


class ResourceNotFoundError(AppError):
    """Raised when a requested resource does not exist."""

    code = ErrorCode.RESOURCE_NOT_FOUND
