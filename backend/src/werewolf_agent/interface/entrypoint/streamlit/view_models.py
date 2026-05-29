"""Pure display models for the Streamlit game screen."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from werewolf_agent.contracts.schemas import (
    PrivateObservationResponse,
    PublicGameState,
    PublicGameTurn,
    PublicPlayerState,
)
from werewolf_agent.interface.entrypoint.streamlit.icons import (
    action_label,
    event_icon,
    phase_label,
    role_label,
    winner_label,
)


@dataclass(frozen=True)
class PlayerSeatView:
    """One compact player seat in the game table."""

    player_id: str
    name: str
    status: str
    activity: str
    is_alive: bool
    is_human: bool


@dataclass(frozen=True)
class TimelineItemView:
    """One public timeline row."""

    sequence: int
    icon: str
    tone: str
    title: str
    detail: str
    time_text: str
    day_label: str


@dataclass(frozen=True)
class ObservationView:
    """Private information visible only to the controlled player."""

    role: str
    available_actions: list[str]
    known_role_lines: list[str]
    target_candidates: dict[str, list[str]]


@dataclass(frozen=True)
class GameScreenView:
    """Single display model for the playable Streamlit screen."""

    game_id: str
    phase: str
    phase_label: str
    day_label: str
    status_label: str
    alive_label: str
    turn_label: str
    winner_label: str
    seats: list[PlayerSeatView]
    timeline: list[TimelineItemView]
    observation: ObservationView | None
    current_turn_title: str
    current_turn_detail: str


def build_game_screen_view(
    *,
    state: PublicGameState,
    turns: list[PublicGameTurn],
    observation: PrivateObservationResponse | None,
    human_player_id: str | None,
) -> GameScreenView:
    """Build a complete display model from public state and optional observation."""
    observation_view = (
        observation_view_from_response(observation, state=state, human_player_id=human_player_id)
        if observation is not None
        else None
    )
    return GameScreenView(
        game_id=state.game_id,
        phase=state.phase,
        phase_label=phase_label(state.phase),
        day_label=f"Day {state.day}",
        status_label="進行中" if state.status == "running" else "終了",
        alive_label=f"{len(state.alive_player_ids)} / {len(state.players)} 人",
        turn_label=f"{state.version} 巡目",
        winner_label=winner_label(state.winner),
        seats=player_seats(state.players, turns=turns, human_player_id=human_player_id),
        timeline=timeline_items(turns),
        observation=observation_view,
        current_turn_title=current_turn_title(state, observation_view, human_player_id),
        current_turn_detail=current_turn_detail(state, observation_view),
    )


def player_seats(
    players: list[PublicPlayerState],
    *,
    turns: list[PublicGameTurn],
    human_player_id: str | None,
) -> list[PlayerSeatView]:
    """Return compact game-table player seats."""
    last_speaker = _last_actor(turns, event_type="speech_recorded")
    seats: list[PlayerSeatView] = []
    for player in players:
        is_human = player.id == human_player_id
        if not player.alive:
            activity = "退場"
        elif player.id == last_speaker:
            activity = "発言済み"
        elif is_human:
            activity = "あなた"
        else:
            activity = "待機中"
        seats.append(
            PlayerSeatView(
                player_id=player.id,
                name=player.name,
                status="生存" if player.alive else "退場",
                activity=activity,
                is_alive=player.alive,
                is_human=is_human,
            )
        )
    return seats


def timeline_items(turns: list[PublicGameTurn]) -> list[TimelineItemView]:
    """Return public timeline rows without exposing raw payloads."""
    return [
        TimelineItemView(
            sequence=turn.sequence,
            icon=event_icon(turn.event_type).symbol,
            tone=event_icon(turn.event_type).tone,
            title=_event_title(turn),
            detail=_event_detail(turn),
            time_text=_time_text(turn.occurred_at),
            day_label=f"Day {turn.day}" if turn.day is not None else "-",
        )
        for turn in turns
    ]


def observation_view_from_response(
    response: PrivateObservationResponse,
    *,
    state: PublicGameState,
    human_player_id: str | None,
) -> ObservationView:
    """Return private observation display data."""
    observation = response.observation
    role = _nested_text(observation, "me", "role")
    actions = [str(item) for item in observation.get("available_actions", [])]
    known_roles = observation.get("known_roles")
    known_role_lines = (
        [
            f"{player_id}: {role_label(role_id)}"
            for player_id, role_id in sorted(known_roles.items())
        ]
        if isinstance(known_roles, dict)
        else []
    )
    return ObservationView(
        role=role_label(role),
        available_actions=actions,
        known_role_lines=known_role_lines,
        target_candidates={
            action: target_candidates_for_action(
                action,
                state=state,
                observation=observation,
                human_player_id=human_player_id,
            )
            for action in actions
        },
    )


def target_candidates_for_action(
    action_type: str,
    *,
    state: PublicGameState,
    observation: dict[str, Any],
    human_player_id: str | None,
) -> list[str]:
    """Return visible player ids that can be offered as target candidates."""
    alive_ids = [player.id for player in state.players if player.alive]
    if action_type == "knight_guard":
        return alive_ids
    if action_type == "werewolf_attack":
        known_roles = observation.get("known_roles")
        werewolves = (
            {str(player_id) for player_id, role in known_roles.items() if role == "werewolf"}
            if isinstance(known_roles, dict)
            else set()
        )
        return [
            player_id
            for player_id in alive_ids
            if player_id != human_player_id and player_id not in werewolves
        ]
    if action_type in {"vote", "seer_inspect"}:
        return [player_id for player_id in alive_ids if player_id != human_player_id]
    return []


def current_turn_title(
    state: PublicGameState,
    observation: ObservationView | None,
    human_player_id: str | None,
) -> str:
    """Return the current hand title."""
    if state.status == "completed":
        return "ゲームは終了しました"
    if observation is not None and observation.available_actions:
        actor = human_player_id or "あなた"
        return f"{actor} の入力待ち"
    return "進行できます"


def current_turn_detail(state: PublicGameState, observation: ObservationView | None) -> str:
    """Return the current hand detail text."""
    if state.status == "completed":
        return f"勝利: {winner_label(state.winner)}"
    if observation is None:
        return "操作するプレイヤーと操作用 token を入力すると手番が表示されます。"
    if observation.available_actions:
        labels = " / ".join(action_label(action) for action in observation.available_actions)
        return f"できる行動: {labels}"
    return "次の入力が必要な場面まで進められます。"


def _event_title(turn: PublicGameTurn) -> str:
    icon = event_icon(turn.event_type)
    if turn.event_type == "phase_started":
        phase = str(turn.payload.get("phase", turn.phase or ""))
        return f"{phase_label(phase)}フェーズ開始"
    return icon.label


def _event_detail(turn: PublicGameTurn) -> str:
    actor = turn.actor_id or str(turn.payload.get("player_id", ""))
    if turn.event_type == "game_started":
        player_count = turn.payload.get("player_count")
        if player_count:
            return f"{player_count}人でゲームが始まりました。"
        return "ゲームが始まりました。"
    if turn.event_type == "speech_recorded":
        return f"{actor} が発言しました。" if actor else "プレイヤーが発言しました。"
    if turn.event_type == "vote_recorded":
        return f"{actor} が投票しました。" if actor else "投票が行われました。"
    if turn.event_type == "night_action_recorded":
        return "夜の行動が実行されました。詳細は表示されません。"
    if turn.event_type == "game_finished":
        winner = turn.payload.get("winner")
        if isinstance(winner, str):
            return f"{winner_label(winner)}の勝利です。"
        return "勝敗が決まりました。"
    if turn.event_type == "phase_started":
        return "次の場面に進みました。"
    return "出来事が記録されました。"


def _last_actor(turns: list[PublicGameTurn], *, event_type: str) -> str | None:
    for turn in reversed(turns):
        if turn.event_type == event_type:
            return turn.actor_id or _payload_text(turn.payload, "player_id")
    return None


def _payload_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return str(value) if value is not None else None


def _nested_text(payload: dict[str, Any], parent: str, child: str) -> str:
    value = payload.get(parent)
    if isinstance(value, dict):
        child_value = value.get(child)
        return str(child_value) if child_value is not None else ""
    return ""


def _time_text(value: datetime) -> str:
    return value.strftime("%H:%M:%S")
