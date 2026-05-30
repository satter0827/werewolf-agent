"""Default Streamlit UI icon and label mappings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UiIcon:
    """Small UI marker that can later be replaced by image assets."""

    symbol: str
    label: str
    tone: str = "neutral"


DEFAULT_EVENT_ICON = UiIcon("•", "出来事")
DEFAULT_ACTION_ICON = UiIcon("•", "行動")
DEFAULT_STATUS_ICON = UiIcon("•", "状態")

EVENT_ICONS: dict[str, UiIcon] = {
    "game_started": UiIcon("▶", "ゲーム開始", "day"),
    "phase_started": UiIcon("↪", "フェーズ開始", "day"),
    "speech_recorded": UiIcon("💬", "発言", "safe"),
    "vote_recorded": UiIcon("☑", "投票", "safe"),
    "voting_resolved": UiIcon("⚖", "投票結果", "day"),
    "night_started": UiIcon("◐", "夜の始まり", "danger"),
    "night_action_recorded": UiIcon("◌", "夜の行動", "danger"),
    "night_resolved": UiIcon("◑", "夜明け", "danger"),
    "game_finished": UiIcon("🏁", "決着", "danger"),
}

ACTION_ICONS: dict[str, UiIcon] = {
    "speech": UiIcon("💬", "発言", "safe"),
    "vote": UiIcon("☑", "投票", "day"),
    "werewolf_attack": UiIcon("◆", "襲撃", "danger"),
    "seer_inspect": UiIcon("◇", "占い", "safe"),
    "knight_guard": UiIcon("◈", "護衛", "safe"),
    "pass": UiIcon("▷", "パス", "neutral"),
}

ACTION_LABELS: dict[str, str] = {
    "speech": "発言",
    "vote": "投票",
    "werewolf_attack": "襲撃",
    "seer_inspect": "占い",
    "knight_guard": "護衛",
    "pass": "パス",
}

STATUS_ICONS: dict[str, UiIcon] = {
    "phase": UiIcon("◌", "現在のフェーズ", "day"),
    "next_update": UiIcon("↻", "次の更新", "day"),
    "alive": UiIcon("●", "生存プレイヤー", "safe"),
    "turn": UiIcon("▶", "経過ターン", "day"),
    "hand": UiIcon("✋", "現在の手番", "danger"),
    "player": UiIcon("●", "あなた", "neutral"),
    "updated": UiIcon("↺", "最終更新", "neutral"),
    "status": UiIcon("■", "状態", "neutral"),
    "winner": UiIcon("🏁", "勝利", "neutral"),
}

PHASE_LABELS: dict[str, str] = {
    "night": "夜",
    "day_discussion": "話し合い",
    "voting": "投票",
    "finished": "終了",
}

ROLE_LABELS: dict[str, str] = {
    "villager": "村人",
    "werewolf": "人狼",
    "seer": "占い師",
    "knight": "騎士",
}

WINNER_LABELS: dict[str, str] = {
    "villagers": "村人陣営",
    "werewolves": "人狼陣営",
}


def event_icon(event_type: str) -> UiIcon:
    """Return the configured marker for one public timeline event."""
    return EVENT_ICONS.get(event_type, DEFAULT_EVENT_ICON)


def action_icon(action_type: str) -> UiIcon:
    """Return the configured marker for one action."""
    return ACTION_ICONS.get(action_type, DEFAULT_ACTION_ICON)


def action_label(action_type: str) -> str:
    """Return a human-facing action label."""
    return ACTION_LABELS.get(action_type, action_type.replace("_", " "))


def status_icon(status_type: str) -> UiIcon:
    """Return the configured marker for one status metric."""
    return STATUS_ICONS.get(status_type, DEFAULT_STATUS_ICON)


def phase_label(phase: str | None) -> str:
    """Return a human-facing phase label."""
    if phase is None:
        return "-"
    return PHASE_LABELS.get(phase, phase.replace("_", " "))


def role_label(role: object) -> str:
    """Return a human-facing role label."""
    role_text = str(role or "")
    if not role_text:
        return "不明"
    return ROLE_LABELS.get(role_text, role_text)


def winner_label(winner: str | None) -> str:
    """Return a human-facing winner label."""
    if winner is None:
        return "未決着"
    return WINNER_LABELS.get(winner, winner)
