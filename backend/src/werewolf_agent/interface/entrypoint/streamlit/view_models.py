"""Pure display models for the Streamlit game screen."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from werewolf_agent.contracts.schemas import (
    PrivateObservationResponse,
    PublicGameRunSummary,
    PublicGameState,
    PublicGameTurn,
    PublicPlayerState,
)
from werewolf_agent.interface.entrypoint.streamlit.icons import (
    action_icon,
    action_label,
    event_icon,
    phase_label,
    role_label,
    status_icon,
    winner_label,
)


@dataclass(frozen=True)
class PlayerSeatView:
    """One compact player seat in the game table."""

    player_id: str
    name: str
    status: str
    activity: str
    activity_tone: str
    is_alive: bool
    is_human: bool
    is_current: bool


@dataclass(frozen=True)
class StatusMetricView:
    """One top status strip item."""

    key: str
    icon: str
    label: str
    value: str
    detail: str
    tone: str = "neutral"


@dataclass(frozen=True)
class TableLegendItemView:
    """One table legend marker."""

    symbol: str
    label: str
    tone: str


@dataclass(frozen=True)
class ActionChoiceView:
    """One action option visible in the hand panel."""

    action_type: str
    icon: str
    label: str
    requires_target: bool
    requires_message: bool


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
    action_choices: list[ActionChoiceView]
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
    status_metrics: list[StatusMetricView]
    table_legend: list[TableLegendItemView]
    seats: list[PlayerSeatView]
    timeline: list[TimelineItemView]
    observation: ObservationView | None
    current_turn_title: str
    current_turn_detail: str
    is_completed: bool
    can_submit_action: bool


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
    can_submit_action = (
        state.status != "completed"
        and observation_view is not None
        and bool(observation_view.available_actions)
    )
    current_title = current_turn_title(state, observation_view, human_player_id)
    current_detail = current_turn_detail(state, observation_view)
    return GameScreenView(
        game_id=state.game_id,
        phase=state.phase,
        phase_label=phase_label(state.phase),
        day_label=f"Day {state.day}",
        status_label="進行中" if state.status == "running" else "終了",
        alive_label=f"{len(state.alive_player_ids)} / {len(state.players)} 人",
        turn_label=f"{state.version} 巡目",
        winner_label=winner_label(state.winner),
        status_metrics=status_metrics(
            state,
            current_turn=current_title,
            current_turn_detail=current_detail,
        ),
        table_legend=table_legend_items(),
        seats=player_seats(
            state.players,
            turns=turns,
            observation=observation_view,
            human_player_id=human_player_id,
        ),
        timeline=timeline_items(turns),
        observation=observation_view,
        current_turn_title=current_title,
        current_turn_detail=current_detail,
        is_completed=state.status == "completed",
        can_submit_action=can_submit_action,
    )


def status_metrics(
    state: PublicGameState,
    *,
    current_turn: str,
    current_turn_detail: str,
) -> list[StatusMetricView]:
    """Return top status strip items."""
    metrics = [
        ("phase", "現在のフェーズ", f"Day {state.day} {phase_label(state.phase)}", ""),
        ("alive", "生存プレイヤー", f"{len(state.alive_player_ids)} / {len(state.players)} 人", ""),
        ("turn", "経過ターン", f"{state.version} 巡目", ""),
        ("hand", "現在の手番", current_turn, current_turn_detail),
        ("status", "状態", "進行中" if state.status == "running" else "終了", ""),
        ("winner", "勝利", winner_label(state.winner), ""),
    ]
    return [
        StatusMetricView(
            key=key,
            icon=status_icon(key).symbol,
            label=label,
            value=value,
            detail=detail,
            tone=status_icon(key).tone,
        )
        for key, label, value, detail in metrics
    ]


def table_legend_items() -> list[TableLegendItemView]:
    """Return stable legend items for the game table."""
    return [
        TableLegendItemView("●", "発言済み", "safe"),
        TableLegendItemView("●", "入力待ち", "danger"),
        TableLegendItemView("●", "待機中", "neutral"),
        TableLegendItemView("x", "退場", "muted"),
    ]


def player_seats(
    players: list[PublicPlayerState],
    *,
    turns: list[PublicGameTurn],
    observation: ObservationView | None,
    human_player_id: str | None,
) -> list[PlayerSeatView]:
    """Return compact game-table player seats."""
    last_speaker = _last_actor(turns, event_type="speech_recorded")
    active_player_id = (
        human_player_id
        if observation is not None and observation.available_actions
        else last_speaker
    )
    seats: list[PlayerSeatView] = []
    for player in players:
        is_human = player.id == human_player_id
        is_current = player.id == active_player_id
        if not player.alive:
            activity = "退場"
            activity_tone = "muted"
        elif is_human and observation is not None and observation.available_actions:
            activity = "入力待ち"
            activity_tone = "danger"
        elif player.id == last_speaker:
            activity = "発言済み"
            activity_tone = "safe"
        elif is_human:
            activity = "あなた"
            activity_tone = "danger"
        else:
            activity = "待機中"
            activity_tone = "neutral"
        seats.append(
            PlayerSeatView(
                player_id=player.id,
                name=player.name,
                status="生存" if player.alive else "退場",
                activity=activity,
                activity_tone=activity_tone,
                is_alive=player.alive,
                is_human=is_human,
                is_current=is_current,
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
        action_choices=[action_choice(action) for action in actions],
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


def action_choice(action_type: str) -> ActionChoiceView:
    """Return display metadata for one action."""
    return ActionChoiceView(
        action_type=action_type,
        icon=action_icon(action_type).symbol,
        label=action_label(action_type),
        requires_target=action_type in {"vote", "werewolf_attack", "seer_inspect", "knight_guard"},
        requires_message=action_type == "speech",
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
        return "あなたの入力待ち"
    if observation is None and human_player_id:
        return "ゲームを確認中"
    return "進行できます"


def current_turn_detail(state: PublicGameState, observation: ObservationView | None) -> str:
    """Return the current hand detail text."""
    if state.status == "completed":
        return f"勝利: {winner_label(state.winner)}"
    if observation is None:
        return "ゲームを再開すると、あなたの手番が表示されます。"
    if observation.available_actions:
        labels = " / ".join(action_label(action) for action in observation.available_actions)
        return f"できる行動: {labels}"
    return "次の入力が必要な場面まで進められます。"


def game_run_option_label(run: PublicGameRunSummary) -> str:
    """Return one sidebar option label for a game run."""
    status = "終了" if run.status == "completed" else "進行中"
    return f"{status} / Day {run.day} / {run.game_id}"


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
        return "夜の行動が進みました。"
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
