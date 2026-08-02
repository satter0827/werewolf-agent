"""timeline projections for the Streamlit game screen."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werewolf_agent.clients.streamlit.constants import UNKNOWN_VALUE_LABEL
from werewolf_agent.clients.streamlit.i18n import I18nCatalog, Language
from werewolf_agent.clients.streamlit.icons import event_icon
from werewolf_agent.clients.streamlit.view_models.actions import _theme_term, _winner_label
from werewolf_agent.clients.streamlit.view_models.formatting import (
    _day_label,
    _player_label,
    _player_list_label,
    _player_name_map,
    _time_text,
)
from werewolf_agent.clients.streamlit.view_models.types import (
    ObserverLogView,
    ResultSummaryView,
    TimelineItemView,
)
from werewolf_agent.contracts.schemas import (
    GAME_STATUS_COMPLETED,
    GameTimelineItem,
    PublicGameState,
)


def timeline_items(
    turns: list[GameTimelineItem],
    *,
    state: PublicGameState,
    catalog: I18nCatalog,
    lang: Language,
) -> list[TimelineItemView]:
    """Return public timeline rows without exposing raw payloads."""
    player_names = _player_name_map(state.players)
    return [
        TimelineItemView(
            sequence=turn.sequence,
            icon=event_icon(turn.event_type).symbol,
            tone=event_icon(turn.event_type).tone,
            title=_event_title(turn, state, catalog, lang),
            detail=turn.narration
            or _event_detail(
                turn,
                state=state,
                player_names=player_names,
                catalog=catalog,
                lang=lang,
            ),
            time_text=_time_text(turn.occurred_at),
            day_label=_day_label(turn.day, catalog, lang) if turn.day is not None else "-",
        )
        for turn in turns
    ]


def observer_log_view(
    timeline: list[TimelineItemView],
    catalog: I18nCatalog,
    lang: Language,
) -> ObserverLogView:
    """Return observer-only lines from the allowlisted public timeline."""
    return ObserverLogView(
        title=catalog.t(lang, "game.observer.log.title"),
        entries_title=catalog.t(lang, "game.observer.log.events"),
        entries=[f"{item.day_label} {item.title}: {item.detail}" for item in timeline[-8:]],
        empty_text=catalog.t(lang, "game.observer.log.empty"),
    )


def result_summary_view(
    state: PublicGameState,
    *,
    turns: list[GameTimelineItem],
    catalog: I18nCatalog,
    lang: Language,
) -> ResultSummaryView | None:
    """Return a completed-game summary after the public timeline."""
    if state.status != GAME_STATUS_COMPLETED:
        return None
    public_names = _player_name_map(state.players)
    facts = [
        catalog.t(lang, "result.fact.winner", winner=_winner_label(state, catalog, lang)),
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
                    state=state,
                    player_names=public_names,
                    catalog=catalog,
                    lang=lang,
                ),
            )
        )
    return ResultSummaryView(
        title=catalog.t(lang, "result.title"),
        detail=catalog.t(lang, "result.detail_play"),
        facts=facts,
    )


def _event_title(
    turn: GameTimelineItem,
    state: PublicGameState,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    if turn.event_type == "phase_started":
        phase = str(turn.payload.get("phase", turn.phase or ""))
        return (
            f"{_theme_term(state, 'phase_names', phase, catalog.label(lang, 'phase', phase))} "
            f"{catalog.label(lang, 'event', 'phase_started')}"
        )
    if "vote" in turn.event_type:
        return _theme_term(
            state, "action_names", "vote", catalog.label(lang, "event", turn.event_type)
        )
    if "night" in turn.event_type:
        return _theme_term(
            state, "phase_names", "night", catalog.label(lang, "event", turn.event_type)
        )
    if turn.event_type == "speech_recorded":
        return _theme_term(
            state, "action_names", "speech", catalog.label(lang, "event", turn.event_type)
        )
    return catalog.label(lang, "event", turn.event_type if turn.event_type else UNKNOWN_VALUE_LABEL)


def _event_detail(
    turn: GameTimelineItem,
    *,
    state: PublicGameState,
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
        message = str(turn.payload.get("utterance", ""))
        has_message = bool(message.strip(" \t\n\r\f\v"))
        if has_message and actor_label:
            return catalog.t(
                lang,
                "event_detail.speech_with_actor",
                actor=actor_label,
                message=message,
            )
        if has_message:
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
                winner=_winner_label(state, catalog, lang),
            )
        return catalog.t(lang, "event_detail.game_finished")
    if turn.event_type == "phase_started":
        return catalog.t(lang, "event_detail.phase_started")
    return catalog.t(lang, "event_detail.unknown")


def _last_actor(turns: list[GameTimelineItem], *, event_type: str) -> str | None:
    for turn in reversed(turns):
        if turn.event_type == event_type:
            return turn.actor_id or _payload_text(turn.payload, "player_id")
    return None


def _payload_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return str(value) if value is not None else None
