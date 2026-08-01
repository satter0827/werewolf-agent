import pytest

from werewolf_agent.clients.presentation import present_error
from werewolf_agent.clients.presentation.errors import PresentationLanguage
from werewolf_agent.contracts import AppError, ErrorCode


def test_japanese_error_presentation_uses_consistent_user_facing_text() -> None:
    error = AppError(
        "Supabase Auth is unavailable.",
        code=ErrorCode.API_UNAVAILABLE,
    )

    presentation = present_error(error, language="ja")

    assert presentation.detail == "APIに接続できません。"
    assert presentation.next_action == "少し待ってから再試行してください。"


def test_english_error_presentation_preserves_safe_context() -> None:
    error = AppError(
        "Supabase Auth is unavailable.",
        code=ErrorCode.API_UNAVAILABLE,
    )

    presentation = present_error(error, language="en")

    assert presentation.detail == "Supabase Auth is unavailable."
    assert presentation.next_action == "Wait briefly, then try again."


def test_japanese_error_presentation_uses_the_stable_message_for_japanese_detail() -> None:
    error = AppError(
        "継続取得ではjsonl出力を使用してください。",
        code=ErrorCode.CONFIG_INVALID_VALUE,
    )

    presentation = present_error(error, language="ja")

    assert presentation.detail == "設定に不備があります。"


@pytest.mark.parametrize("code", tuple(ErrorCode))
@pytest.mark.parametrize("language", ("ja", "en"))
def test_every_error_code_has_a_complete_presentation(
    code: ErrorCode,
    language: PresentationLanguage,
) -> None:
    """すべての安定codeを両言語で安全な画面状態へ変換する。"""
    presentation = present_error(AppError(code=code), language=language)

    assert presentation.detail
    assert presentation.code == code.value


def test_setup_revision_conflict_tells_the_user_to_reload() -> None:
    """競合時は最新の設定版を読み直す具体的な復旧方法を示す。"""
    presentation = present_error(
        AppError(code=ErrorCode.SETUP_REVISION_CONFLICT),
        language="ja",
    )

    assert presentation.detail == "別の操作で新しい設定版が保存されています。"
    assert presentation.next_action == "最新の状態を読み込み直してください。"
