"""決定的なゲーム規則が返す例外を定義する."""

from __future__ import annotations

from collections.abc import Mapping


class RuleViolation(ValueError):
    """安定したmachine-readable codeを持つ拒否済みゲームcommandを表す."""

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        context: Mapping[str, object] | None = None,
    ) -> None:
        """安定したcodeと安全なcontextで規則違反を初期化する."""
        self.code = code
        self.detail = detail
        self.context = dict(context or {})
        super().__init__(detail)


class GameError(RuleViolation):
    """拒否されたゲームactionを表す."""

    def __init__(
        self,
        detail: str,
        *,
        context: Mapping[str, object] | None = None,
    ) -> None:
        """不正actionの規則違反を初期化する."""
        super().__init__("invalid_action", detail, context=context)


class GamePhaseError(RuleViolation):
    """拒否されたゲームphase遷移を表す."""

    def __init__(
        self,
        detail: str,
        *,
        context: Mapping[str, object] | None = None,
    ) -> None:
        """不正phaseの規則違反を初期化する."""
        super().__init__("invalid_phase", detail, context=context)


__all__ = ["GameError", "GamePhaseError", "RuleViolation"]
