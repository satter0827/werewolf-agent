"""Application facadeへ渡す検証済み呼出主体を定義する."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Actor:
    """外側のsecurity境界が検証した呼出主体を表す."""

    user_id: str
    is_anonymous: bool = False
    is_admin: bool = False

    def __post_init__(self) -> None:
        """安定した外部subject IDを正規化して必須とする."""
        user_id = self.user_id.strip()
        if not user_id:
            raise ValueError("Actor user_id must not be blank.")
        object.__setattr__(self, "user_id", user_id)


__all__: list[str] = []
