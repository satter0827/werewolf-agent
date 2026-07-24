"""Errors raised by deterministic game rules."""

from __future__ import annotations

from collections.abc import Mapping


class RuleViolation(ValueError):
    """A rejected game command with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        context: Mapping[str, object] | None = None,
    ) -> None:
        """Initialize a violation with a stable code and safe context."""
        self.code = code
        self.detail = detail
        self.context = dict(context or {})
        super().__init__(detail)


class GameError(RuleViolation):
    """A rejected game action."""

    def __init__(
        self,
        detail: str,
        *,
        context: Mapping[str, object] | None = None,
    ) -> None:
        """Initialize an invalid-action violation."""
        super().__init__("invalid_action", detail, context=context)


class GamePhaseError(RuleViolation):
    """A rejected game phase transition."""

    def __init__(
        self,
        detail: str,
        *,
        context: Mapping[str, object] | None = None,
    ) -> None:
        """Initialize an invalid-phase violation."""
        super().__init__("invalid_phase", detail, context=context)


__all__ = ["GameError", "GamePhaseError", "RuleViolation"]
