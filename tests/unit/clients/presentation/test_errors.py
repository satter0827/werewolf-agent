from werewolf_agent.clients.presentation import present_error
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


def test_japanese_error_presentation_preserves_specific_japanese_guidance() -> None:
    error = AppError(
        "継続取得ではjsonl出力を使用してください。",
        code=ErrorCode.CONFIG_INVALID_VALUE,
    )

    presentation = present_error(error, language="ja")

    assert presentation.detail == "継続取得ではjsonl出力を使用してください。"
