"""Pure display models for the Streamlit play screen."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from werewolf_agent.contracts.schemas import (
    GameTimelineItem,
    PlayerObservationResponse,
    PublicGameRunSummary,
    PublicGameState,
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

ScreenMode = Literal["playable", "observer"]


@dataclass(frozen=True)
class SavedGameOptionView:
    """One save option shown in the sidebar selector."""

    option_id: str
    label: str
    game_id: str
    mode: ScreenMode
    human_player_id: str | None = None
    control_token: str = ""


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
class HandPanelView:
    """Right-side player hand panel state."""

    title: str
    detail: str
    tone: str
    advance_title: str
    advance_detail: str
    can_advance: bool


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
    screen_mode: ScreenMode
    status: str
    phase: str
    phase_label: str
    day_label: str
    status_label: str
    alive_label: str
    turn_label: str
    player_label: str
    updated_label: str
    winner_label: str
    player_count: int
    alive_count: int
    status_metrics: list[StatusMetricView]
    table_legend: list[TableLegendItemView]
    seats: list[PlayerSeatView]
    timeline: list[TimelineItemView]
    hand_panel: HandPanelView
    observation: ObservationView | None
    current_turn_title: str
    current_turn_detail: str
    is_completed: bool
    can_submit_action: bool


def build_game_screen_view(
    *,
    state: PublicGameState,
    turns: list[GameTimelineItem],
    observation: PlayerObservationResponse | None,
    human_player_id: str | None,
    screen_mode: ScreenMode | None = None,
    refresh_interval_seconds: float = 0,
) -> GameScreenView:
    """Build a complete display model from public state and optional observation."""
    effective_mode: ScreenMode = screen_mode or (
        "playable" if observation is not None else "observer"
    )
    observation_view = (
        observation_view_from_response(observation, state=state, human_player_id=human_player_id)
        if observation is not None
        else None
    )
    can_submit_action = (
        effective_mode == "playable"
        and state.status != "completed"
        and observation_view is not None
        and bool(observation_view.available_actions)
    )
    current_title = current_turn_title(state, observation_view, effective_mode)
    current_detail = current_turn_detail(state, observation_view, effective_mode)
    human_label = _human_player_label(state.players, human_player_id, effective_mode)
    updated_label = _optional_time_text(state.updated_at)
    return GameScreenView(
        game_id=state.game_id,
        screen_mode=effective_mode,
        status=state.status,
        phase=state.phase,
        phase_label=phase_label(state.phase),
        day_label=f"Day {state.day}",
        status_label="進行中" if state.status == "running" else "終了",
        alive_label=f"{len(state.alive_player_ids)} / {len(state.players)} 人",
        turn_label=f"{state.version} ターン目",
        player_label=human_label,
        updated_label=updated_label,
        winner_label=winner_label(state.winner),
        player_count=len(state.players),
        alive_count=len(state.alive_player_ids),
        status_metrics=status_metrics(
            state,
            current_turn=current_title,
            current_turn_detail=current_detail,
            human_label=human_label,
            updated_label=updated_label,
            refresh_interval_seconds=refresh_interval_seconds,
        ),
        table_legend=table_legend_items(),
        seats=player_seats(
            state.players,
            turns=turns,
            observation=observation_view,
            human_player_id=human_player_id if effective_mode == "playable" else None,
        ),
        timeline=timeline_items(turns, players=state.players),
        hand_panel=hand_panel_view(state, observation_view, effective_mode),
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
    human_label: str,
    updated_label: str,
    refresh_interval_seconds: float,
) -> list[StatusMetricView]:
    """Return top status strip items."""
    metrics = [
        ("phase", "現在のフェーズ", f"Day {state.day}", phase_label(state.phase)),
        ("next_update", "次の更新", _seconds_label(refresh_interval_seconds), "手動更新もできます"),
        ("alive", "生存プレイヤー", f"{len(state.alive_player_ids)} / {len(state.players)} 人", ""),
        ("turn", "経過ターン", f"{state.version} ターン目", ""),
        (
            "player",
            "あなた",
            human_label,
            current_turn_detail if current_turn == "あなたの入力待ち" else "",
        ),
        ("updated", "最終更新", updated_label, ""),
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
        TableLegendItemView("●", "発言中", "safe"),
        TableLegendItemView("●", "あなたの手番", "danger"),
        TableLegendItemView("●", "未発言", "muted"),
    ]


def player_seats(
    players: list[PublicPlayerState],
    *,
    turns: list[GameTimelineItem],
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
            activity = "未発言"
            activity_tone = "muted"
        seats.append(
            PlayerSeatView(
                player_id=player.id,
                name=_display_player_name(player.name, fallback=player.id),
                status="生存" if player.alive else "退場",
                activity=activity,
                activity_tone=activity_tone,
                is_alive=player.alive,
                is_human=is_human,
                is_current=is_current,
            )
        )
    return seats


def timeline_items(
    turns: list[GameTimelineItem],
    *,
    players: list[PublicPlayerState],
) -> list[TimelineItemView]:
    """Return public timeline rows without exposing raw payloads."""
    player_names = _player_name_map(players)
    return [
        TimelineItemView(
            sequence=turn.sequence,
            icon=event_icon(turn.event_type).symbol,
            tone=event_icon(turn.event_type).tone,
            title=_event_title(turn),
            detail=_event_detail(turn, player_names=player_names),
            time_text=_time_text(turn.occurred_at),
            day_label=f"Day {turn.day}" if turn.day is not None else "-",
        )
        for turn in turns
    ]


def observation_view_from_response(
    response: PlayerObservationResponse,
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
            f"{_player_name(state.players, player_id)}: {role_label(role_id)}"
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


def hand_panel_view(
    state: PublicGameState,
    observation: ObservationView | None,
    screen_mode: ScreenMode,
) -> HandPanelView:
    """Return the right-side hand panel state."""
    if state.status == "completed":
        return HandPanelView(
            title="ゲームは終了しました",
            detail=f"勝利: {winner_label(state.winner)}",
            tone="safe",
            advance_title="最終状態",
            advance_detail="このゲームで追加の入力はありません。",
            can_advance=False,
        )
    if screen_mode == "observer":
        return HandPanelView(
            title="観戦モード",
            detail="公開情報だけを表示しています。",
            tone="neutral",
            advance_title="公開情報",
            advance_detail="手番入力は保存データから再開できる場合だけ表示されます。",
            can_advance=False,
        )
    if observation is not None and observation.available_actions:
        labels = " / ".join(action_label(action) for action in observation.available_actions)
        return HandPanelView(
            title="あなたの入力待ち",
            detail=f"できる行動: {labels}",
            tone="danger",
            advance_title="入力を送信",
            advance_detail="行動を選んで送信してください。",
            can_advance=False,
        )
    return HandPanelView(
        title="進行待ち",
        detail="今はあなたの入力はありません。",
        tone="day",
        advance_title="今できること",
        advance_detail="次にあなたの入力が必要な場面までゲームを進められます。",
        can_advance=True,
    )


def current_turn_title(
    state: PublicGameState,
    observation: ObservationView | None,
    screen_mode: ScreenMode,
) -> str:
    """Return the current hand title."""
    if state.status == "completed":
        return "ゲームは終了しました"
    if screen_mode == "observer":
        return "観戦中"
    if observation is not None and observation.available_actions:
        return "あなたの入力待ち"
    return "進行待ち"


def current_turn_detail(
    state: PublicGameState,
    observation: ObservationView | None,
    screen_mode: ScreenMode,
) -> str:
    """Return the current hand detail text."""
    if state.status == "completed":
        return f"勝利: {winner_label(state.winner)}"
    if screen_mode == "observer":
        return "公開情報だけを表示しています。"
    if observation is not None and observation.available_actions:
        labels = " / ".join(action_label(action) for action in observation.available_actions)
        return f"できる行動: {labels}"
    return "次の入力待ちまで進められます。"


def game_run_option_label(run: PublicGameRunSummary) -> str:
    """Return one human-facing sidebar label without exposing the internal game id."""
    status = "終了" if run.status == "completed" else "進行中"
    return (
        f"{status} / Day {run.day} / {run.player_count}人 / "
        f"最終更新 {_time_text(run.updated_at)} / 観戦のみ"
    )


def _event_title(turn: GameTimelineItem) -> str:
    icon = event_icon(turn.event_type)
    if turn.event_type == "phase_started":
        phase = str(turn.payload.get("phase", turn.phase or ""))
        return f"{phase_label(phase)}フェーズ開始"
    return icon.label


def _event_detail(turn: GameTimelineItem, *, player_names: dict[str, str]) -> str:
    actor = turn.actor_id or str(turn.payload.get("player_id", ""))
    actor_label = _player_label(actor, player_names)
    if turn.event_type == "game_started":
        player_count = turn.payload.get("player_count")
        if player_count:
            return f"{player_count}人でゲームが始まりました。"
        return "ゲームが始まりました。"
    if turn.event_type == "speech_recorded":
        message = str(turn.payload.get("message", "")).strip()
        if message and actor_label:
            return f"{actor_label}: 「{message}」"
        if message:
            return f"「{message}」"
        return f"{actor_label} が発言しました。" if actor_label else "プレイヤーが発言しました。"
    if turn.event_type == "vote_submitted":
        target_label = _player_label(turn.payload.get("target_id"), player_names)
        if actor_label and target_label:
            return f"{actor_label} が {target_label} に投票しました。"
        return "投票が行われました。"
    if turn.event_type == "vote_resolved":
        eliminated = _player_label(turn.payload.get("eliminated_player_id"), player_names)
        if eliminated:
            return f"投票の結果、{eliminated} が退場しました。"
        tied = _player_list_label(turn.payload.get("tied_player_ids"), player_names)
        if tied:
            return f"投票は同数でした: {tied}。退場者はいません。"
        return "投票の結果、退場者はいません。"
    if turn.event_type == "night_resolved":
        killed = _player_label(turn.payload.get("killed_player_id"), player_names)
        if killed:
            return f"夜が明け、{killed} が犠牲になりました。"
        return "夜が明けました。昨夜の犠牲者はいません。"
    if turn.event_type == "game_finished":
        winner = turn.payload.get("winner")
        if isinstance(winner, str):
            return f"{winner_label(winner)}の勝利です。"
        return "勝敗が決まりました。"
    if turn.event_type == "phase_started":
        return "次の場面に進みました。"
    return "出来事が記録されました。"


def _last_actor(turns: list[GameTimelineItem], *, event_type: str) -> str | None:
    for turn in reversed(turns):
        if turn.event_type == event_type:
            return turn.actor_id or _payload_text(turn.payload, "player_id")
    return None


def _payload_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return str(value) if value is not None else None


def _player_name_map(players: list[PublicPlayerState]) -> dict[str, str]:
    return {player.id: _display_player_name(player.name, fallback=player.id) for player in players}


def _player_label(value: object, player_names: dict[str, str]) -> str:
    if value is None:
        return ""
    player_id = str(value)
    return player_names.get(player_id) or _public_actor_label(player_id) or player_id


def _player_list_label(value: object, player_names: dict[str, str]) -> str:
    if not isinstance(value, list):
        return ""
    return "、".join(_player_label(item, player_names) for item in value if item is not None)


def _nested_text(payload: dict[str, Any], parent: str, child: str) -> str:
    value = payload.get(parent)
    if isinstance(value, dict):
        child_value = value.get(child)
        return str(child_value) if child_value is not None else ""
    return ""


def _time_text(value: datetime) -> str:
    return value.strftime("%H:%M:%S")


def _optional_time_text(value: datetime | None) -> str:
    return _time_text(value) if value is not None else "-"


def _seconds_label(value: float) -> str:
    if value <= 0:
        return "手動"
    if value.is_integer():
        return f"{int(value)} 秒"
    return f"{value:.1f} 秒"


def _human_player_label(
    players: list[PublicPlayerState],
    human_player_id: str | None,
    screen_mode: ScreenMode,
) -> str:
    if screen_mode == "observer" or human_player_id is None:
        return "観戦中"
    return _player_name(players, human_player_id)


def _player_name(players: list[PublicPlayerState], player_id: object) -> str:
    player_id_text = str(player_id)
    for player in players:
        if player.id == player_id_text:
            return _display_player_name(player.name, fallback=player.id)
    return _public_actor_label(player_id_text) or player_id_text


def _display_player_name(name: str, *, fallback: str) -> str:
    stripped = name.strip()
    if stripped.startswith("Player "):
        suffix = stripped.removeprefix("Player ").strip()
        if suffix.isdigit():
            return f"P{suffix}"
    return stripped or _public_actor_label(fallback) or fallback


def _public_actor_label(actor_id: str) -> str:
    if not actor_id:
        return ""
    if actor_id.startswith("player-"):
        suffix = actor_id.removeprefix("player-")
        if suffix.isdigit():
            return f"P{suffix}"
    return actor_id
