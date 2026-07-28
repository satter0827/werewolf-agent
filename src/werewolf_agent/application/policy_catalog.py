"""Presentation metadata for rule policies registered by the application."""

from __future__ import annotations

from typing import Any

POLICY_OPTIONS: dict[str, tuple[dict[str, str], ...]] = {
    "action_policies": (
        {
            "id": "standard",
            "name": "標準の行動判定",
            "description": "役職、phase、生存状態に基づいて合法な行動を判定します。",
        },
    ),
    "resolution_policies": (
        {
            "id": "standard",
            "name": "標準の解決",
            "description": "夜の能力と投票を標準ルールで解決します。",
        },
    ),
    "phase_policies": (
        {
            "id": "required_actions",
            "name": "必要行動を待つ",
            "description": "必要な行動が揃ってから次のphaseへ進みます。",
        },
    ),
    "victory_policies": (
        {
            "id": "faction_balance",
            "name": "陣営人数で判定",
            "description": "人狼と村陣営の生存人数から勝敗を判定します。",
        },
    ),
    "visibility_policies": (
        {
            "id": "standard",
            "name": "標準の公開範囲",
            "description": "公開情報と本人だけの観測情報を分離します。",
        },
    ),
}

PHASE_ORDER_OPTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "standard",
        "name": "標準のphase順序",
        "description": "夜、昼の議論、投票の順に進行します。",
        "phases": ("night", "day_discussion", "voting"),
    },
)

__all__ = ["PHASE_ORDER_OPTIONS", "POLICY_OPTIONS"]
