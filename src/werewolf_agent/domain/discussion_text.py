"""議論文の機械判定に使う正規化契約を定義する."""

from __future__ import annotations

from typing import TypeGuard

DISCUSSION_WHITESPACE = frozenset(" \t\n\r\f\v")
_ASCII_CASE_TRANSLATION = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "abcdefghijklmnopqrstuvwxyz",
)


def collapse_discussion_whitespace(value: str) -> str:
    """ASCII空白だけを単一の半角スペースへ畳み込む."""
    parts: list[str] = []
    pending_space = False
    for character in value:
        if character in DISCUSSION_WHITESPACE:
            pending_space = bool(parts)
            continue
        if pending_space:
            parts.append(" ")
        parts.append(character)
        pending_space = False
    return "".join(parts)


def normalize_discussion_utterance(value: str) -> str:
    """空白とASCII英字の大小だけを議論文の比較用に正規化する."""
    return collapse_discussion_whitespace(value).translate(_ASCII_CASE_TRANSLATION)


def is_discussion_utterance(value: object) -> TypeGuard[str]:
    """値が表示文として有効な文字列ならtrueを返す."""
    return isinstance(value, str) and bool(collapse_discussion_whitespace(value))


def validate_discussion_utterance(value: str) -> str:
    """表示文を変更せず、契約上の空白だけからなる値を拒否する."""
    if not is_discussion_utterance(value):
        raise ValueError("utterance must not be blank.")
    return value


__all__ = [
    "DISCUSSION_WHITESPACE",
    "collapse_discussion_whitespace",
    "is_discussion_utterance",
    "normalize_discussion_utterance",
    "validate_discussion_utterance",
]
