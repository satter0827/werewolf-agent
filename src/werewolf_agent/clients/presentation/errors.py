"""Consistent recovery guidance for user-facing clients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.error_catalog import RecoveryAction, get_error_spec
from werewolf_agent.contracts.errors import ErrorCode

PresentationLanguage = Literal["ja", "en"]

_RECOVERY_MESSAGES: dict[PresentationLanguage, dict[RecoveryAction, str]] = {
    "ja": {
        "retry": "少し待ってから再試行してください。",
        "sign_in": "ログイン状態を確認して、もう一度実行してください。",
        "reload": "最新の状態を読み込み直してください。",
        "check_configuration": "設定値と必要なresourceを確認してください。",
        "contact_admin": "管理者に状況とエラーコードを連絡してください。",
        "none": "",
    },
    "en": {
        "retry": "Wait briefly, then try again.",
        "sign_in": "Check your sign-in state, then try again.",
        "reload": "Reload the latest state.",
        "check_configuration": "Check the configuration and required resources.",
        "contact_admin": "Contact an administrator with the error code.",
        "none": "",
    },
}

_JAPANESE_STATE_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.CONFIG_INVALID_VALUE: "設定に不備があります。",
    ErrorCode.REQUEST_VALIDATION_FAILED: "入力内容を確認できませんでした。",
    ErrorCode.REQUEST_RATE_LIMITED: "短時間に操作が集中しています。",
    ErrorCode.REQUEST_BODY_TOO_LARGE: "送信した内容が大きすぎます。",
    ErrorCode.REQUEST_CONCURRENCY_LIMITED: "現在、多くの操作を処理しています。",
    ErrorCode.REQUEST_INVALID_CONTENT_LENGTH: "送信内容の長さを確認できませんでした。",
    ErrorCode.REQUEST_TIMED_OUT: "操作が時間内に完了しませんでした。",
    ErrorCode.REQUEST_IDEMPOTENCY_CONFLICT: "同じ操作の内容が一致しません。",
    ErrorCode.REQUEST_METHOD_NOT_ALLOWED: "この方法では操作できません。",
    ErrorCode.AUTHENTICATION_REQUIRED: "ログイン状態を確認できません。",
    ErrorCode.AUTHORIZATION_FAILED: "この操作を行う権限がありません。",
    ErrorCode.API_UNAVAILABLE: "APIに接続できません。",
    ErrorCode.RESOURCE_NOT_FOUND: "対象が見つかりません。",
    ErrorCode.SETUP_REVISION_CONFLICT: "別の操作で新しい設定版が保存されています。",
    ErrorCode.HTTP_ERROR: "通信を完了できませんでした。",
    ErrorCode.GAME_INVALID_PHASE: "現在のフェーズではこの操作を行えません。",
    ErrorCode.GAME_INVALID_ACTION: "このゲームでは選択した操作を行えません。",
    ErrorCode.AGENT_INVALID_RESPONSE: "agentの応答を確認できませんでした。",
    ErrorCode.LLM_PROVIDER_UNAVAILABLE: "LLM providerに接続できません。",
    ErrorCode.OBSERVATION_WRITE_FAILED: "ゲームの記録を保存できませんでした。",
    ErrorCode.OPERATION_RETRY_EXHAUSTED: "操作を完了できませんでした。",
    ErrorCode.OPERATION_UPGRADE_INTERRUPTED: "操作をもう一度送信する必要があります。",
    ErrorCode.INTERNAL_UNEXPECTED: "予期しない問題が発生しました。",
}


@dataclass(frozen=True)
class ErrorPresentation:
    """Safe error state and the next action a user can take."""

    detail: str
    code: str
    retryable: bool
    recovery: RecoveryAction
    next_action: str


def present_error(error: AppError, *, language: PresentationLanguage) -> ErrorPresentation:
    """Build consistent recovery guidance from the stable error catalog."""
    recovery = get_error_spec(error.code).recovery
    return ErrorPresentation(
        detail=(
            error.detail
            if language == "ja" and _contains_japanese(error.detail)
            else _JAPANESE_STATE_MESSAGES[error.code]
            if language == "ja"
            else error.detail
        ),
        code=error.code.value,
        retryable=error.retryable,
        recovery=recovery,
        next_action=_RECOVERY_MESSAGES[language][recovery],
    )


def _contains_japanese(value: str) -> bool:
    return any(
        "\u3040" <= character <= "\u30ff" or "\u4e00" <= character <= "\u9fff"
        for character in value
    )


__all__ = ["ErrorPresentation", "PresentationLanguage", "present_error"]
