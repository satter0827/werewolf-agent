"""game projections for the Streamlit game screen."""

from __future__ import annotations

from werewolf_agent.clients.streamlit.i18n import I18nCatalog, Language
from werewolf_agent.clients.streamlit.icons import status_icon
from werewolf_agent.clients.streamlit.view_models.actions import (
    _has_available_actions,
    current_turn_detail,
    current_turn_title,
    hand_panel_view,
    observation_view_from_response,
)
from werewolf_agent.clients.streamlit.view_models.formatting import (
    _day_label,
    _display_player_name,
    _manual_player_label,
    _optional_time_text,
    _seconds_label,
    _time_text,
)
from werewolf_agent.clients.streamlit.view_models.timeline import (
    _last_actor,
    observer_log_view,
    result_summary_view,
    timeline_items,
)
from werewolf_agent.clients.streamlit.view_models.types import (
    GameScreenView,
    ObservationMemoView,
    ObservationView,
    PlayerSeatView,
    ScreenMode,
    StatusMetricView,
    TableLegendItemView,
    TimelineItemView,
)
from werewolf_agent.contracts.schemas import (
    GAME_STATUS_COMPLETED,
    GAME_STATUS_RUNNING,
    GameTimelineItem,
    PlayerObservationResponse,
    PublicGameState,
    PublicGameSummary,
    PublicPlayerState,
)


def build_game_screen_view(
    *,
    state: PublicGameState,
    turns: list[GameTimelineItem],
    observation: PlayerObservationResponse | None,
    manual_player_id: str | None,
    screen_mode: ScreenMode | None = None,
    catalog: I18nCatalog,
    lang: Language,
    refresh_interval_seconds: float = 0,
) -> GameScreenView:
    """Build a display model from public data and an optional player observation."""
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
        seed=state.seed,
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
            manual_player_id=manual_player_id if effective_mode == "playable" else None,
            catalog=catalog,
            lang=lang,
        ),
        timeline=public_timeline,
        hand_panel=hand_panel_view(state, observation_view, effective_mode, catalog, lang),
        observation=observation_view,
        observer_log=observer_log_view(public_timeline, catalog, lang)
        if effective_mode == "observer"
        else None,
        result_summary=result_summary_view(
            state,
            turns=turns,
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
    manual_player_id: str | None,
    catalog: I18nCatalog,
    lang: Language,
) -> list[PlayerSeatView]:
    """Return compact game-table player seats."""
    last_speaker = _last_actor(turns, event_type="speech_recorded")
    active_player_id = manual_player_id if _has_available_actions(observation) else last_speaker
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
            )
        )
    return seats


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
