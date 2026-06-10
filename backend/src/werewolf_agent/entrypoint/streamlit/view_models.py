"""Pure display models for the Streamlit play and observer screens."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from werewolf_agent.commons.shared.constants import DEFAULT_NARRATION_MODE, UNKNOWN_VALUE_LABEL
from werewolf_agent.commons.shared.validation import (
    public_generated_player_label,
    public_generated_player_name_label,
)
from werewolf_agent.contracts.schemas import (
    GAME_STATUS_COMPLETED,
    GAME_STATUS_RUNNING,
    CustomCharacterDefinitionRequest,
    CustomRoleDefinitionRequest,
    GameRevealAction,
    GameRevealPlayer,
    GameRevealResponse,
    GameTimelineItem,
    LocalRulesSettings,
    PlayerObservationResponse,
    PublicGameState,
    PublicGameSummary,
    PublicPlayerState,
)
from werewolf_agent.entrypoint.streamlit.i18n import I18nCatalog, Language
from werewolf_agent.entrypoint.streamlit.icons import (
    action_icon,
    event_icon,
    status_icon,
)

ScreenMode = Literal["playable", "observer"]


@dataclass(frozen=True)
class SavedGameOptionView:
    """One save option shown in the sidebar selector."""

    option_id: str
    label: str
    game_id: str
    mode: ScreenMode
    manual_player_id: str | None = None
    manual_token: str = ""
    role_counts: dict[str, int] | None = None
    rules: LocalRulesSettings | None = None
    seed: int | None = None
    scenario_id: str | None = None
    setup_preset_id: str | None = None
    agent_strategy_id: str | None = None
    narration_mode: str = DEFAULT_NARRATION_MODE
    character_assignments: dict[str, str] | None = None
    custom_roles: list[CustomRoleDefinitionRequest] | None = None
    custom_characters: list[CustomCharacterDefinitionRequest] | None = None


@dataclass(frozen=True)
class PlayerSeatView:
    """One compact player seat in the game table."""

    player_id: str
    name: str
    status: str
    activity: str
    activity_tone: str
    is_alive: bool
    is_manual: bool
    is_current: bool
    role_label: str | None = None
    faction_label: str | None = None


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

    heading: str
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
class ObserverLogView:
    """Observer-only reveal summary."""

    title: str
    role_title: str
    role_lines: list[str]
    action_lines: list[str]
    empty_text: str


@dataclass(frozen=True)
class ResultSummaryView:
    """Completed-game result summary displayed after the timeline."""

    title: str
    detail: str
    facts: list[str]


@dataclass(frozen=True)
class ObservationMemoView:
    """Public observation memo shown at the bottom of the right panel."""

    title: str
    updated_label: str
    lines: list[str]


@dataclass(frozen=True)
class GameScreenView:
    """Single display model for the Streamlit game screen."""

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
    role_counts: dict[str, int]
    rules: LocalRulesSettings | None
    seed: int | None
    status_metrics: list[StatusMetricView]
    table_legend: list[TableLegendItemView]
    seats: list[PlayerSeatView]
    timeline: list[TimelineItemView]
    hand_panel: HandPanelView
    observation: ObservationView | None
    observer_log: ObserverLogView | None
    result_summary: ResultSummaryView | None
    observation_memo: ObservationMemoView
    current_turn_title: str
    current_turn_detail: str
    is_completed: bool
    can_submit_action: bool


def build_game_screen_view(
    *,
    state: PublicGameState,
    turns: list[GameTimelineItem],
    observation: PlayerObservationResponse | None,
    reveal: GameRevealResponse | None,
    manual_player_id: str | None,
    screen_mode: ScreenMode | None = None,
    catalog: I18nCatalog,
    lang: Language,
    refresh_interval_seconds: float = 0,
) -> GameScreenView:
    """Build a complete display model from public state and optional private/reveal data."""
    effective_mode: ScreenMode = screen_mode or (
        "playable" if observation is not None else "observer"
    )
    observation_view = (
        observation_view_from_response(
            observation,
            state=state,
            manual_player_id=manual_player_id,
            catalog=catalog,
            lang=lang,
        )
        if observation is not None and effective_mode == "playable"
        else None
    )
    can_submit_action = (
        effective_mode == "playable"
        and state.status != GAME_STATUS_COMPLETED
        and observation_view is not None
        and bool(observation_view.available_actions)
    )
    current_title = current_turn_title(state, observation_view, effective_mode, catalog, lang)
    current_detail = current_turn_detail(state, observation_view, effective_mode, catalog, lang)
    manual_label = _manual_player_label(
        state.players,
        manual_player_id,
        effective_mode,
        catalog,
        lang,
    )
    updated_label = _optional_time_text(state.updated_at, catalog, lang)
    role_counts = dict(reveal.role_counts) if reveal is not None else {}
    public_timeline = timeline_items(turns, players=state.players, catalog=catalog, lang=lang)
    return GameScreenView(
        game_id=state.game_id,
        screen_mode=effective_mode,
        status=state.status,
        phase=state.phase,
        phase_label=catalog.label(lang, "phase", state.phase),
        day_label=_day_label(state.day, catalog, lang),
        status_label=catalog.t(lang, "status.running")
        if state.status == GAME_STATUS_RUNNING
        else catalog.t(lang, "status.completed"),
        alive_label=f"{len(state.alive_player_ids)} / {len(state.players)}",
        turn_label=f"{state.version}",
        player_label=manual_label,
        updated_label=updated_label,
        winner_label=catalog.label(lang, "winner", state.winner),
        player_count=len(state.players),
        alive_count=len(state.alive_player_ids),
        role_counts=role_counts,
        rules=reveal.rules if reveal is not None else None,
        seed=reveal.seed if reveal is not None else state.seed,
        status_metrics=status_metrics(
            state,
            current_turn=current_title,
            current_turn_detail=current_detail,
            manual_label=manual_label,
            updated_label=updated_label,
            refresh_interval_seconds=refresh_interval_seconds,
            catalog=catalog,
            lang=lang,
        ),
        table_legend=table_legend_items(catalog, lang),
        seats=player_seats(
            state.players,
            turns=turns,
            observation=observation_view,
            reveal=reveal,
            manual_player_id=manual_player_id if effective_mode == "playable" else None,
            catalog=catalog,
            lang=lang,
        ),
        timeline=public_timeline,
        hand_panel=hand_panel_view(state, observation_view, effective_mode, catalog, lang),
        observation=observation_view,
        observer_log=(
            observer_log_view(reveal, catalog, lang) if effective_mode == "observer" else None
        ),
        result_summary=result_summary_view(
            state,
            turns=turns,
            reveal=reveal if effective_mode == "observer" else None,
            catalog=catalog,
            lang=lang,
        ),
        observation_memo=observation_memo_view(
            state,
            timeline=public_timeline,
            observation=observation_view,
            screen_mode=effective_mode,
            catalog=catalog,
            lang=lang,
        ),
        current_turn_title=current_title,
        current_turn_detail=current_detail,
        is_completed=state.status == GAME_STATUS_COMPLETED,
        can_submit_action=can_submit_action,
    )


def status_metrics(
    state: PublicGameState,
    *,
    current_turn: str,
    current_turn_detail: str,
    manual_label: str,
    updated_label: str,
    refresh_interval_seconds: float,
    catalog: I18nCatalog,
    lang: Language,
) -> list[StatusMetricView]:
    """Return top status strip items."""
    metrics = [
        (
            "phase",
            catalog.t(lang, "metric.phase"),
            _day_label(state.day, catalog, lang),
            catalog.label(lang, "phase", state.phase),
        ),
        (
            "next_update",
            catalog.t(lang, "metric.next_update"),
            _seconds_label(refresh_interval_seconds, catalog, lang),
            "",
        ),
        (
            "alive",
            catalog.t(lang, "metric.alive"),
            f"{len(state.alive_player_ids)} / {len(state.players)}",
            "",
        ),
        ("turn", catalog.t(lang, "metric.turn"), str(state.version), ""),
        (
            "player",
            catalog.t(lang, "metric.player"),
            manual_label,
            current_turn_detail if current_turn == catalog.t(lang, "game.current.playable") else "",
        ),
        ("updated", catalog.t(lang, "metric.updated"), updated_label, ""),
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


def table_legend_items(catalog: I18nCatalog, lang: Language) -> list[TableLegendItemView]:
    """Return stable legend items for the game table."""
    return [
        TableLegendItemView("●", catalog.label(lang, "activity", "acted"), "safe"),
        TableLegendItemView("●", catalog.label(lang, "activity", "current"), "safe"),
        TableLegendItemView("●", catalog.label(lang, "activity", "input"), "danger"),
        TableLegendItemView("●", catalog.label(lang, "activity", "idle"), "muted"),
    ]


def player_seats(
    players: list[PublicPlayerState],
    *,
    turns: list[GameTimelineItem],
    observation: ObservationView | None,
    reveal: GameRevealResponse | None,
    manual_player_id: str | None,
    catalog: I18nCatalog,
    lang: Language,
) -> list[PlayerSeatView]:
    """Return compact game-table player seats."""
    last_speaker = _last_actor(turns, event_type="speech_recorded")
    active_player_id = manual_player_id if _has_available_actions(observation) else last_speaker
    reveal_players = {player.id: player for player in reveal.players} if reveal is not None else {}
    seats: list[PlayerSeatView] = []
    for player in players:
        is_manual = player.id == manual_player_id
        is_current = player.id == active_player_id
        if not player.alive:
            activity = catalog.label(lang, "activity", "dead")
            activity_tone = "muted"
        elif is_manual and observation is not None and observation.available_actions:
            activity = catalog.label(lang, "activity", "input")
            activity_tone = "danger"
        elif player.id == last_speaker:
            activity = catalog.label(lang, "activity", "acted")
            activity_tone = "safe"
        elif is_manual:
            activity = catalog.label(lang, "activity", "manual")
            activity_tone = "danger"
        else:
            activity = catalog.label(lang, "activity", "idle")
            activity_tone = "muted"
        reveal_player = reveal_players.get(player.id)
        seats.append(
            PlayerSeatView(
                player_id=player.id,
                name=_display_player_name(player.name, fallback=player.id),
                status=(
                    catalog.t(lang, "status.alive")
                    if player.alive
                    else catalog.t(lang, "status.dead")
                ),
                activity=activity,
                activity_tone=activity_tone,
                is_alive=player.alive,
                is_manual=is_manual,
                is_current=is_current,
                role_label=catalog.label(lang, "role", reveal_player.role)
                if reveal_player is not None
                else None,
                faction_label=catalog.label(lang, "faction", reveal_player.faction)
                if reveal_player is not None
                else None,
            )
        )
    return seats


def timeline_items(
    turns: list[GameTimelineItem],
    *,
    players: list[PublicPlayerState],
    catalog: I18nCatalog,
    lang: Language,
) -> list[TimelineItemView]:
    """Return public timeline rows without exposing raw payloads."""
    player_names = _player_name_map(players)
    return [
        TimelineItemView(
            sequence=turn.sequence,
            icon=event_icon(turn.event_type).symbol,
            tone=event_icon(turn.event_type).tone,
            title=_event_title(turn, catalog, lang),
            detail=turn.narration
            or _event_detail(turn, player_names=player_names, catalog=catalog, lang=lang),
            time_text=_time_text(turn.occurred_at),
            day_label=_day_label(turn.day, catalog, lang) if turn.day is not None else "-",
        )
        for turn in turns
    ]


def observation_view_from_response(
    response: PlayerObservationResponse,
    *,
    state: PublicGameState,
    manual_player_id: str | None,
    catalog: I18nCatalog,
    lang: Language,
) -> ObservationView:
    """Return private observation display data."""
    observation = response.observation
    role = _nested_text(observation, "me", "role")
    actions = [str(item) for item in observation.get("available_actions", [])]
    known_roles = observation.get("known_roles")
    known_role_lines = (
        [
            f"{_player_name(state.players, player_id)}: {catalog.label(lang, 'role', role_id)}"
            for player_id, role_id in sorted(known_roles.items())
        ]
        if isinstance(known_roles, dict)
        else []
    )
    return ObservationView(
        role=catalog.label(lang, "role", role),
        available_actions=actions,
        action_choices=[action_choice(action, catalog, lang) for action in actions],
        known_role_lines=known_role_lines,
        target_candidates={
            action: target_candidates_for_action(
                action,
                state=state,
                observation=observation,
                manual_player_id=manual_player_id,
            )
            for action in actions
        },
    )


def action_choice(action_type: str, catalog: I18nCatalog, lang: Language) -> ActionChoiceView:
    """Return display metadata for one action."""
    return ActionChoiceView(
        action_type=action_type,
        icon=action_icon(action_type).symbol,
        label=catalog.label(lang, "action", action_type),
        requires_target=action_type in {"vote", "werewolf_attack", "seer_inspect", "knight_guard"},
        requires_message=action_type == "speech",
    )


def target_candidates_for_action(
    action_type: str,
    *,
    state: PublicGameState,
    observation: dict[str, Any],
    manual_player_id: str | None,
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
            if player_id != manual_player_id and player_id not in werewolves
        ]
    if action_type in {"vote", "seer_inspect"}:
        return [player_id for player_id in alive_ids if player_id != manual_player_id]
    return []


def hand_panel_view(
    state: PublicGameState,
    observation: ObservationView | None,
    screen_mode: ScreenMode,
    catalog: I18nCatalog,
    lang: Language,
) -> HandPanelView:
    """Return the right-side hand panel state."""
    heading = (
        catalog.t(lang, "game.observer.title")
        if screen_mode == "observer"
        else catalog.t(lang, "game.hand.heading")
    )
    if state.status == GAME_STATUS_COMPLETED:
        return HandPanelView(
            heading=heading,
            title=catalog.t(lang, "game.completed.title"),
            detail=catalog.t(
                lang,
                "result.fact.winner",
                winner=catalog.label(lang, "winner", state.winner),
            ),
            tone="safe",
            advance_title=catalog.t(lang, "game.completed.title"),
            advance_detail=catalog.t(lang, "game.completed.detail"),
            can_advance=False,
        )
    if screen_mode == "observer":
        return HandPanelView(
            heading=catalog.t(lang, "game.observer.title"),
            title=catalog.t(lang, "game.observer.title"),
            detail=catalog.t(lang, "game.observer.detail"),
            tone="neutral",
            advance_title=catalog.t(lang, "game.observer.title"),
            advance_detail=catalog.t(lang, "game.observer.detail"),
            can_advance=False,
        )
    if observation is not None and observation.available_actions:
        labels = " / ".join(
            catalog.label(lang, "action", action) for action in observation.available_actions
        )
        return HandPanelView(
            heading=heading,
            title=catalog.t(lang, "game.current.playable"),
            detail=f"{labels}",
            tone="danger",
            advance_title=catalog.t(lang, "action.send"),
            advance_detail=catalog.t(lang, "game.current.playable"),
            can_advance=False,
        )
    return HandPanelView(
        heading=heading,
        title=catalog.t(lang, "game.play.waiting.title"),
        detail=catalog.t(lang, "game.play.waiting.detail"),
        tone="day",
        advance_title=catalog.t(lang, "game.advance.title"),
        advance_detail=catalog.t(lang, "game.advance.detail"),
        can_advance=True,
    )


def observer_log_view(
    reveal: GameRevealResponse | None,
    catalog: I18nCatalog,
    lang: Language,
) -> ObserverLogView:
    """Return observer-only reveal log lines."""
    if reveal is None:
        return ObserverLogView(
            title=catalog.t(lang, "game.observer.log.title"),
            role_title=catalog.t(lang, "game.observer.log.roles"),
            role_lines=[],
            action_lines=[],
            empty_text=catalog.t(lang, "game.observer.log.empty"),
        )
    player_names = _reveal_player_name_map(reveal.players)
    role_lines = [
        f"{_display_player_name(player.name, fallback=player.id)}: "
        f"{catalog.label(lang, 'role', player.role)} / "
        f"{catalog.label(lang, 'faction', player.faction)}"
        for player in reveal.players
    ]
    action_lines = [
        *[_action_line(action, player_names, catalog, lang) for action in reveal.pending_votes],
        *[
            _action_line(action, player_names, catalog, lang)
            for action in reveal.pending_night_actions
        ],
    ]
    if reveal.votes:
        latest = reveal.votes[-1]
        action_lines.append(
            catalog.t(
                lang,
                "result.fact.last_vote",
                player=_player_label(latest.eliminated_player_id, player_names)
                or catalog.t(lang, "common.none"),
            )
        )
    if reveal.nights:
        latest_night = reveal.nights[-1]
        action_lines.append(
            catalog.t(
                lang,
                "result.fact.last_night",
                attacked=_player_label(latest_night.attacked_player_id, player_names)
                or catalog.t(lang, "common.none"),
                guarded=_player_label(latest_night.protected_player_id, player_names)
                or catalog.t(lang, "common.none"),
                killed=_player_label(latest_night.killed_player_id, player_names)
                or catalog.t(lang, "common.none"),
            )
        )
    return ObserverLogView(
        title=catalog.t(lang, "game.observer.log.title"),
        role_title=catalog.t(lang, "game.observer.log.roles"),
        role_lines=role_lines,
        action_lines=action_lines,
        empty_text=catalog.t(lang, "game.observer.log.empty"),
    )


def result_summary_view(
    state: PublicGameState,
    *,
    turns: list[GameTimelineItem],
    reveal: GameRevealResponse | None,
    catalog: I18nCatalog,
    lang: Language,
) -> ResultSummaryView | None:
    """Return a completed-game summary after the public timeline."""
    if state.status != GAME_STATUS_COMPLETED:
        return None
    public_names = _player_name_map(state.players)
    facts = [
        catalog.t(lang, "result.fact.winner", winner=catalog.label(lang, "winner", state.winner)),
        catalog.t(lang, "result.fact.finish_day", day=state.day),
        catalog.t(
            lang,
            "result.fact.survivors",
            names=_player_list_label(state.alive_player_ids, public_names)
            or catalog.t(lang, "common.none"),
        ),
        catalog.t(
            lang,
            "result.fact.eliminated",
            names=_player_list_label(state.eliminated_player_ids, public_names)
            or catalog.t(lang, "common.none"),
        ),
    ]
    if turns:
        last_turn = turns[-1]
        facts.append(
            catalog.t(
                lang,
                "result.fact.last_event",
                detail=_event_detail(
                    last_turn,
                    player_names=public_names,
                    catalog=catalog,
                    lang=lang,
                ),
            )
        )
    detail = catalog.t(lang, "result.detail_play")
    if reveal is not None:
        reveal_names = _reveal_player_name_map(reveal.players)
        role_lines = [
            f"{_display_player_name(player.name, fallback=player.id)}="
            f"{catalog.label(lang, 'role', player.role)}"
            for player in reveal.players
        ]
        facts.append(catalog.t(lang, "result.fact.roles", roles=", ".join(role_lines)))
        if reveal.votes:
            facts.append(
                catalog.t(
                    lang,
                    "result.fact.last_vote",
                    player=_player_label(reveal.votes[-1].eliminated_player_id, reveal_names)
                    or catalog.t(lang, "common.none"),
                )
            )
        if reveal.nights:
            latest_night = reveal.nights[-1]
            facts.append(
                catalog.t(
                    lang,
                    "result.fact.last_night",
                    attacked=_player_label(latest_night.attacked_player_id, reveal_names)
                    or catalog.t(lang, "common.none"),
                    guarded=_player_label(latest_night.protected_player_id, reveal_names)
                    or catalog.t(lang, "common.none"),
                    killed=_player_label(latest_night.killed_player_id, reveal_names)
                    or catalog.t(lang, "common.none"),
                )
            )
        detail = catalog.t(lang, "result.detail_observer")
    return ResultSummaryView(title=catalog.t(lang, "result.title"), detail=detail, facts=facts)


def observation_memo_view(
    state: PublicGameState,
    *,
    timeline: list[TimelineItemView],
    observation: ObservationView | None,
    screen_mode: ScreenMode,
    catalog: I18nCatalog,
    lang: Language,
) -> ObservationMemoView:
    """Return a public-only table summary for the right panel."""
    lines = [
        catalog.t(
            lang,
            "observation_memo.alive",
            alive=len(state.alive_player_ids),
            total=len(state.players),
        ),
        catalog.t(
            lang,
            "observation_memo.phase",
            phase=catalog.label(lang, "phase", state.phase),
            day=_day_label(state.day, catalog, lang),
        ),
    ]
    if state.status == GAME_STATUS_COMPLETED:
        lines.append(
            catalog.t(
                lang,
                "observation_memo.completed",
                winner=catalog.label(lang, "winner", state.winner),
            )
        )
    elif screen_mode == "observer":
        lines.append(catalog.t(lang, "observation_memo.observer"))
    elif _has_available_actions(observation):
        lines.append(catalog.t(lang, "observation_memo.input_required"))
    else:
        lines.append(catalog.t(lang, "observation_memo.waiting"))

    if timeline:
        latest = timeline[-1]
        lines.append(
            catalog.t(
                lang,
                "observation_memo.latest",
                event=f"{latest.title}: {latest.detail}",
            )
        )
    else:
        lines.append(catalog.t(lang, "observation_memo.latest_empty"))

    return ObservationMemoView(
        title=catalog.t(lang, "observation_memo.title"),
        updated_label=catalog.t(
            lang,
            "observation_memo.updated",
            time=_optional_time_text(state.updated_at, catalog, lang),
        ),
        lines=lines,
    )


def current_turn_title(
    state: PublicGameState,
    observation: ObservationView | None,
    screen_mode: ScreenMode,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    """Return the current hand title."""
    if state.status == GAME_STATUS_COMPLETED:
        return catalog.t(lang, "game.completed.title")
    if screen_mode == "observer":
        return catalog.t(lang, "game.current.observer")
    if observation is not None and observation.available_actions:
        return catalog.t(lang, "game.current.playable")
    return catalog.t(lang, "game.play.waiting.title")


def current_turn_detail(
    state: PublicGameState,
    observation: ObservationView | None,
    screen_mode: ScreenMode,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    """Return the current hand detail text."""
    if state.status == GAME_STATUS_COMPLETED:
        return catalog.t(
            lang,
            "result.fact.winner",
            winner=catalog.label(lang, "winner", state.winner),
        )
    if screen_mode == "observer":
        return catalog.t(lang, "game.observer.detail")
    if observation is not None and observation.available_actions:
        labels = " / ".join(
            catalog.label(lang, "action", action) for action in observation.available_actions
        )
        return labels
    return catalog.t(lang, "game.play.waiting.detail")


def game_option_label(
    game: PublicGameSummary,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    """Return one sidebar label without exposing the internal game id."""
    status = (
        catalog.t(lang, "status.completed")
        if game.status == GAME_STATUS_COMPLETED
        else catalog.t(lang, "status.running")
    )
    return (
        f"{status} / {_day_label(game.day, catalog, lang)} / {game.player_count} / "
        f"{catalog.t(lang, 'metric.updated')} {_time_text(game.updated_at)} / "
        f"{catalog.t(lang, 'setup.mode.observe')}"
    )


def _event_title(turn: GameTimelineItem, catalog: I18nCatalog, lang: Language) -> str:
    if turn.event_type == "phase_started":
        phase = str(turn.payload.get("phase", turn.phase or ""))
        return (
            f"{catalog.label(lang, 'phase', phase)} {catalog.label(lang, 'event', 'phase_started')}"
        )
    return catalog.label(lang, "event", turn.event_type if turn.event_type else UNKNOWN_VALUE_LABEL)


def _event_detail(
    turn: GameTimelineItem,
    *,
    player_names: Mapping[str, str],
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    actor = turn.actor_id or str(turn.payload.get("player_id", ""))
    actor_label = _player_label(actor, player_names)
    if turn.event_type == "game_started":
        player_count = turn.payload.get("player_count")
        if player_count:
            return catalog.t(
                lang,
                "event_detail.game_started_with_count",
                player_count=player_count,
            )
        return catalog.t(lang, "event_detail.game_started")
    if turn.event_type == "speech_recorded":
        message = str(turn.payload.get("message", "")).strip()
        if message and actor_label:
            return catalog.t(
                lang,
                "event_detail.speech_with_actor",
                actor=actor_label,
                message=message,
            )
        if message:
            return catalog.t(lang, "event_detail.speech_message", message=message)
        if actor_label:
            return catalog.t(lang, "event_detail.speech_actor", actor=actor_label)
        return catalog.label(lang, "event", "speech_recorded")
    if turn.event_type == "vote_submitted":
        target_label = _player_label(turn.payload.get("target_id"), player_names)
        if actor_label and target_label:
            return catalog.t(
                lang,
                "event_detail.vote_submitted_with_target",
                actor=actor_label,
                target=target_label,
            )
        return catalog.t(lang, "event_detail.vote_submitted")
    if turn.event_type == "vote_resolved":
        eliminated = _player_label(turn.payload.get("eliminated_player_id"), player_names)
        if eliminated:
            return catalog.t(
                lang,
                "event_detail.vote_resolved_eliminated",
                player=eliminated,
            )
        tied = _player_list_label(turn.payload.get("tied_player_ids"), player_names)
        if tied:
            return catalog.t(
                lang,
                "event_detail.vote_resolved_tied",
                players=tied,
            )
        return catalog.t(lang, "event_detail.vote_resolved_none")
    if turn.event_type == "night_resolved":
        killed = _player_label(turn.payload.get("killed_player_id"), player_names)
        if killed:
            return catalog.t(lang, "event_detail.night_resolved_killed", player=killed)
        return catalog.t(lang, "event_detail.night_resolved_none")
    if turn.event_type == "game_finished":
        winner = turn.payload.get("winner")
        if isinstance(winner, str):
            return catalog.t(
                lang,
                "event_detail.game_finished_winner",
                winner=catalog.label(lang, "winner", winner),
            )
        return catalog.t(lang, "event_detail.game_finished")
    if turn.event_type == "phase_started":
        return catalog.t(lang, "event_detail.phase_started")
    return catalog.t(lang, "event_detail.unknown")


def _action_line(
    action: GameRevealAction,
    player_names: Mapping[str, str],
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    actor = _player_label(action.player_id, player_names)
    target = _player_label(action.target_id, player_names) or catalog.t(lang, "common.none")
    return f"{actor}: {catalog.label(lang, 'action', action.type)} -> {target}"


def _last_actor(turns: list[GameTimelineItem], *, event_type: str) -> str | None:
    for turn in reversed(turns):
        if turn.event_type == event_type:
            return turn.actor_id or _payload_text(turn.payload, "player_id")
    return None


def _payload_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return str(value) if value is not None else None


def _has_available_actions(observation: ObservationView | None) -> bool:
    return observation is not None and bool(observation.available_actions)


def _player_name_map(players: list[PublicPlayerState]) -> dict[str, str]:
    return {player.id: _display_player_name(player.name, fallback=player.id) for player in players}


def _reveal_player_name_map(players: list[GameRevealPlayer]) -> dict[str, str]:
    return {player.id: _display_player_name(player.name, fallback=player.id) for player in players}


def _player_label(value: object, player_names: Mapping[str, str]) -> str:
    if value is None:
        return ""
    player_id = str(value)
    return player_names.get(player_id) or _public_actor_label(player_id) or player_id


def _player_list_label(value: object, player_names: Mapping[str, str]) -> str:
    if not isinstance(value, list):
        return ""
    return ", ".join(_player_label(item, player_names) for item in value if item is not None)


def _nested_text(payload: dict[str, Any], parent: str, child: str) -> str:
    value = payload.get(parent)
    if isinstance(value, dict):
        child_value = value.get(child)
        return str(child_value) if child_value is not None else ""
    return ""


def _time_text(value: datetime) -> str:
    return value.strftime("%H:%M:%S")


def _optional_time_text(value: datetime | None, catalog: I18nCatalog, lang: Language) -> str:
    return _time_text(value) if value is not None else catalog.t(lang, "game.updated.empty")


def _day_label(value: int, catalog: I18nCatalog, lang: Language) -> str:
    return catalog.t(lang, "time.day", day=value)


def _seconds_label(value: float, catalog: I18nCatalog, lang: Language) -> str:
    if value <= 0:
        return catalog.t(lang, "time.manual")
    seconds: int | str = int(value) if value.is_integer() else f"{value:.1f}"
    return catalog.t(lang, "time.seconds", seconds=seconds)


def _manual_player_label(
    players: list[PublicPlayerState],
    manual_player_id: str | None,
    screen_mode: ScreenMode,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    if screen_mode == "observer" or manual_player_id is None:
        return catalog.t(lang, "metric.player_observer")
    return _player_name(players, manual_player_id)


def _player_name(players: list[PublicPlayerState], player_id: object) -> str:
    player_id_text = str(player_id)
    for player in players:
        if player.id == player_id_text:
            return _display_player_name(player.name, fallback=player.id)
    return _public_actor_label(player_id_text) or player_id_text


def _display_player_name(name: str, *, fallback: str) -> str:
    stripped = name.strip()
    return (
        public_generated_player_name_label(stripped)
        or stripped
        or _public_actor_label(fallback)
        or fallback
    )


def _public_actor_label(actor_id: str) -> str:
    if not actor_id:
        return ""
    return public_generated_player_label(actor_id) or actor_id
