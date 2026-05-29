"""Streamlit observer console for the public Werewolf Agent API."""

from __future__ import annotations

import html
import importlib
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar, cast

from pydantic import ValidationError

from werewolf_agent.commons.configuration import (
    AppSettings,
    configure_interface_logging,
    get_settings,
    settings_error_detail,
)
from werewolf_agent.commons.shared.messages import (
    LOG_STREAMLIT_ACTION_SUBMITTED,
    LOG_STREAMLIT_APPLICATION_ERROR_HANDLED,
    LOG_STREAMLIT_CONNECTION_CHECKED,
    LOG_STREAMLIT_GAME_CREATED,
    LOG_STREAMLIT_GAME_STEPPED,
    LOG_STREAMLIT_REFRESHED,
)
from werewolf_agent.contracts import AppError, ConfigError
from werewolf_agent.contracts.schemas import (
    GameEventsResponse,
    GameResponse,
    GameRunsResponse,
    GameTurnsResponse,
    PrivateObservationResponse,
    PublicGameState,
    SubmitPlayerActionRequest,
)
from werewolf_agent.interface.entrypoint.streamlit.i18n import (
    LANGUAGE_NAMES,
    Language,
    normalize_language,
    text,
)
from werewolf_agent.interface.entrypoint.streamlit.view_models import (
    ObserverHint,
    TimelineItem,
    build_observer_hint,
    build_player_status_rows,
    build_timeline_items_from_events,
    build_timeline_items_from_turns,
    resolve_phase_style,
)
from werewolf_agent.interface.shared import workflows
from werewolf_agent.interface.shared.api_client import GameApiClient, build_game_api_client
from werewolf_agent.interface.shared.game_requests import build_create_game_request

st = cast(Any, importlib.import_module("streamlit"))
logger = logging.getLogger(__name__)
T = TypeVar("T")
ClientFactory = Callable[[str, float], GameApiClient]


def default_client_factory(api_url: str, timeout: float) -> GameApiClient:
    """Build the default public API client."""
    return build_game_api_client(api_url, timeout=timeout)


def render_app(
    *,
    settings: AppSettings | None = None,
    client_factory: ClientFactory = default_client_factory,
) -> None:
    """Render the Streamlit application."""
    try:
        loaded_settings = settings or get_settings()
        configure_interface_logging(
            loaded_settings,
            service_name=loaded_settings.streamlit_service_name,
        )
    except ValidationError as exc:
        _render_configuration_error(ConfigError(settings_error_detail(exc)))
        return

    st.set_page_config(page_title=loaded_settings.streamlit_page_title, layout="wide")
    _inject_css()
    _init_session(loaded_settings)

    language = _render_language_control(loaded_settings)
    api_url = _render_api_url_control(loaded_settings, language)
    client = client_factory(api_url, loaded_settings.streamlit_http_timeout_seconds)
    health = _check_connection(client, language=language, api_url=api_url)
    runs = _load_runs(client, loaded_settings, language) if health is not None else None
    active_game_id, auto_refresh = _render_sidebar(
        client=client,
        settings=loaded_settings,
        language=language,
        runs=runs,
        health=health,
    )
    _render_main_console(
        client=client,
        settings=loaded_settings,
        language=language,
        active_game_id=active_game_id,
        runs=runs,
        auto_refresh=auto_refresh,
    )


def _render_configuration_error(error: AppError) -> None:
    st.set_page_config(page_title="Werewolf Agent", layout="wide")
    st.error(error.detail)


def _init_session(settings: AppSettings) -> None:
    defaults: dict[str, object] = {
        "active_game_id": "",
        "control_tokens": {},
        "human_player_id": "player-1",
        "language": settings.streamlit_language,
        "last_observation": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _render_language_control(settings: AppSettings) -> Language:
    _render_sidebar_brand(settings)
    configured = normalize_language(
        str(st.session_state.get("language", settings.streamlit_language))
    )
    labels = [LANGUAGE_NAMES["ja"], LANGUAGE_NAMES["en"]]
    label_to_language = {LANGUAGE_NAMES[key]: key for key in LANGUAGE_NAMES}
    selected = st.sidebar.selectbox(
        text(configured, "language"),
        labels,
        index=0 if configured == "ja" else 1,
    )
    language = normalize_language(str(label_to_language.get(str(selected), "ja")))
    st.session_state["language"] = language
    return language


def _render_sidebar_brand(settings: AppSettings) -> None:
    st.sidebar.markdown(
        f"""
        <div class="wa-sidebar-brand">
          <div class="wa-brand-mark">W</div>
          <div>
            <div class="wa-brand-title">{_escape(settings.streamlit_page_title)}</div>
            <div class="wa-brand-caption">Observer Console</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_api_url_control(settings: AppSettings, language: Language) -> str:
    st.sidebar.header(text(language, "api_connection"))
    return str(
        st.sidebar.text_input(
            text(language, "api_url"),
            value=settings.streamlit_resolved_api_url,
        )
    )


def _check_connection(
    client: GameApiClient,
    *,
    language: Language,
    api_url: str,
) -> dict[str, str] | None:
    health = _safe_call(language, lambda: workflows.check_health(client))
    logger.info(
        LOG_STREAMLIT_CONNECTION_CHECKED,
        extra={
            "api_url": api_url,
            "connected": health is not None,
            "api_service": health.get("service", "") if health is not None else "",
        },
    )
    return health


def _render_sidebar(
    *,
    client: GameApiClient,
    settings: AppSettings,
    language: Language,
    runs: GameRunsResponse | None,
    health: dict[str, str] | None,
) -> tuple[str, bool]:
    if health is None:
        st.sidebar.error(text(language, "connection_failed"))
    else:
        st.sidebar.success(text(language, "connection_ok"))

    st.sidebar.divider()
    active_game_id = _render_game_selector(runs=runs, language=language)
    _render_create_game_controls(client=client, settings=settings, language=language)
    auto_refresh = _render_refresh_controls(settings=settings, language=language)
    _render_sidebar_nav(language)
    return active_game_id, auto_refresh


def _render_game_selector(
    *,
    runs: GameRunsResponse | None,
    language: Language,
) -> str:
    st.sidebar.header(text(language, "active_game"))
    run_ids = [run.game_id for run in runs.runs] if runs is not None else []
    active_game_id = str(st.session_state.get("active_game_id", ""))
    if active_game_id and active_game_id not in run_ids:
        run_ids.insert(0, active_game_id)
    if not run_ids:
        st.sidebar.info(text(language, "no_active_game"))
        return active_game_id

    selected = st.sidebar.selectbox(
        text(language, "active_game"),
        run_ids,
        index=run_ids.index(active_game_id) if active_game_id in run_ids else 0,
    )
    active_game_id = str(selected)
    st.session_state["active_game_id"] = active_game_id
    return active_game_id


def _render_create_game_controls(
    *,
    client: GameApiClient,
    settings: AppSettings,
    language: Language,
) -> None:
    st.sidebar.divider()
    st.sidebar.header(text(language, "create_game"))
    players = int(
        st.sidebar.number_input(
            text(language, "players"),
            min_value=settings.game_min_players,
            max_value=settings.game_max_players,
            value=settings.game_default_player_count,
            step=1,
        )
    )
    seed_label = text(language, "seed")
    seed_text = str(st.sidebar.text_input(seed_label, value="1")).strip()
    seed = _parse_optional_int(seed_text, label=seed_label, language=language)
    include_human = bool(st.sidebar.checkbox(text(language, "use_human_player"), value=False))
    human_player = None
    if include_human:
        player_options = [f"player-{index}" for index in range(1, players + 1)]
        human_player = str(st.sidebar.selectbox(text(language, "human_player"), player_options))

    if st.sidebar.button(text(language, "create_game"), type="primary"):
        if seed is _INVALID_INTEGER:
            return
        request = build_create_game_request(
            players=players,
            seed=cast(int | None, seed),
            human_player=human_player,
            role_count_entries=[],
            tie_break_policy="no_elimination",
            day_speech_turns=1,
            allow_self_vote=False,
            default_player_count=settings.game_default_player_count,
        )
        created = _safe_call(language, lambda: workflows.create_game(client, request))
        if created is None:
            return
        st.session_state["active_game_id"] = created.game_id
        if created.control_tokens:
            control_tokens = _session_control_tokens()
            control_tokens.update(created.control_tokens)
            st.session_state["control_tokens"] = control_tokens
        logger.info(
            LOG_STREAMLIT_GAME_CREATED,
            extra={"game_id": created.game_id, "human_player": human_player},
        )
        st.sidebar.success(text(language, "created_game"))
        st.rerun()


def _render_refresh_controls(*, settings: AppSettings, language: Language) -> bool:
    st.sidebar.divider()
    st.sidebar.header(text(language, "refresh_controls"))
    auto_refresh = bool(st.sidebar.checkbox(text(language, "auto_refresh"), value=False))
    if st.sidebar.button(text(language, "manual_refresh")):
        logger.info(LOG_STREAMLIT_REFRESHED, extra={"trigger": "manual"})
        st.rerun()
    if auto_refresh and settings.streamlit_refresh_interval_seconds > 0:
        interval = max(1, int(settings.streamlit_refresh_interval_seconds))
        st.markdown(
            f"<meta http-equiv='refresh' content='{interval}'>",
            unsafe_allow_html=True,
        )
    return auto_refresh


def _render_sidebar_nav(language: Language) -> None:
    st.sidebar.divider()
    st.sidebar.header(text(language, "nav"))
    st.sidebar.radio(
        text(language, "nav"),
        [
            text(language, "nav_observe"),
            text(language, "nav_manage"),
            text(language, "nav_diagnostics"),
        ],
        index=0,
        label_visibility="collapsed",
    )


def _render_main_console(
    *,
    client: GameApiClient,
    settings: AppSettings,
    language: Language,
    active_game_id: str,
    runs: GameRunsResponse | None,
    auto_refresh: bool,
) -> None:
    last_refreshed_at = datetime.now().astimezone()
    if not active_game_id:
        _render_empty_console(language=language, runs=runs, auto_refresh=auto_refresh)
        return

    game = _safe_call(language, lambda: workflows.get_game(client, active_game_id))
    if game is None:
        return

    turns = _safe_call(
        language,
        lambda: workflows.list_turns(client, active_game_id, limit=settings.streamlit_turn_limit),
    )
    events = _safe_call(
        language,
        lambda: workflows.list_events(client, active_game_id, limit=settings.streamlit_event_limit),
    )
    timeline_items = _timeline_items(turns=turns, events=events)
    turn_count = _turn_count_for_game(
        runs=runs,
        game_id=active_game_id,
        fallback=max((item.sequence for item in timeline_items), default=0),
    )

    _render_status_strip(
        client=client,
        game=game,
        language=language,
        turn_count=turn_count,
        last_refreshed_at=last_refreshed_at,
    )
    timeline_column, side_column = st.columns([2.35, 1.0], gap="medium")
    with timeline_column:
        _render_timeline(timeline_items, language=language)
        _render_events_panel(events, language=language)
    with side_column:
        _render_observer_hint(build_observer_hint(game.state), game.state, language=language)
        _render_player_status_panel(game.state, language=language)
        _render_human_action_panel(client=client, language=language, state=game.state)
        _render_update_panel(
            auto_refresh=auto_refresh,
            last_refreshed_at=last_refreshed_at,
            language=language,
        )
        _render_runs_panel(runs, language=language)


def _render_empty_console(
    *,
    language: Language,
    runs: GameRunsResponse | None,
    auto_refresh: bool,
) -> None:
    _render_empty_status_strip(language)
    timeline_column, side_column = st.columns([2.35, 1.0], gap="medium")
    with timeline_column:
        st.subheader(text(language, "game_flow"))
        st.info(text(language, "no_active_game"))
    with side_column:
        _render_update_panel(
            auto_refresh=auto_refresh,
            last_refreshed_at=datetime.now().astimezone(),
            language=language,
        )
        _render_runs_panel(runs, language=language)


def _render_empty_status_strip(language: Language) -> None:
    columns = st.columns(5, gap="small")
    values = [
        (text(language, "phase"), "-"),
        (text(language, "alive_players"), "-"),
        (text(language, "elapsed_turns"), "-"),
        (text(language, "last_refreshed"), _format_clock(datetime.now().astimezone())),
        (text(language, "current_winner"), text(language, "winner_pending")),
    ]
    for column, (label, value) in zip(columns, values, strict=True):
        with column:
            _metric_card(label, value)


def _render_status_strip(
    *,
    client: GameApiClient,
    game: GameResponse,
    language: Language,
    turn_count: int,
    last_refreshed_at: datetime,
) -> None:
    state = game.state
    columns = st.columns([1.1, 1.0, 1.0, 1.0, 1.0, 0.95], gap="small")
    phase_label = _phase_label(state.phase, state.day, language)
    values = [
        (text(language, "phase"), phase_label),
        (text(language, "alive_players"), f"{len(state.alive_player_ids)} / {len(state.players)}"),
        (text(language, "elapsed_turns"), str(turn_count)),
        (text(language, "last_refreshed"), _format_clock(last_refreshed_at)),
        (text(language, "current_winner"), state.winner or text(language, "winner_pending")),
    ]
    for column, (label, value) in zip(columns[:5], values, strict=True):
        with column:
            _metric_card(label, value)
    with columns[5]:
        if st.button(text(language, "step_game"), type="primary", width="stretch"):
            stepped = _safe_call(language, lambda: workflows.step_game(client, game.game_id))
            if stepped is not None:
                logger.info(LOG_STREAMLIT_GAME_STEPPED, extra={"game_id": game.game_id})
                st.success(text(language, "stepped_game"))
                st.rerun()


def _metric_card(label: str, value: object) -> None:
    st.markdown(
        f"""
        <div class="wa-metric-card">
          <div class="wa-metric-label">{_escape(label)}</div>
          <div class="wa-metric-value">{_escape(value)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_timeline(items: list[TimelineItem], *, language: Language) -> None:
    st.subheader(text(language, "game_flow"))
    st.caption(text(language, "game_flow_caption"))
    if not items:
        st.info(text(language, "timeline_empty"))
        return

    for item in items:
        _render_timeline_item(item, language=language)


def _render_timeline_item(item: TimelineItem, *, language: Language) -> None:
    day_label = _phase_label(item.phase, item.day, language)
    title = _timeline_title(item, language)
    meta_parts = [
        f"{text(language, 'source')}: {item.source}",
        f"{text(language, 'event_type')}: {item.event_type}",
    ]
    if item.actor_id:
        meta_parts.append(f"actor_id: {item.actor_id}")
    meta = " | ".join(meta_parts)
    st.markdown(
        f"""
        <div class="wa-timeline-row">
          <div class="wa-timeline-marker" style="border-color:{item.style.border};">
            <div class="wa-phase-pill" style="color:{item.style.accent};">
              {_escape(day_label)}
            </div>
            <div class="wa-timeline-time">{_escape(_format_clock(item.occurred_at))}</div>
          </div>
          <div class="wa-timeline-card"
               style="border-color:{item.style.border}; background:{item.style.background};">
            <div class="wa-timeline-card-accent" style="background:{item.style.accent};"></div>
            <div class="wa-timeline-content">
              <div class="wa-timeline-title">{_escape(title)}</div>
              <div class="wa-timeline-summary">
                {_escape(text(language, item.summary_key))}
              </div>
              <div class="wa-timeline-meta">{_escape(meta)}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander(f"{text(language, 'detail')} #{item.sequence}"):
        st.json(
            {
                "source": item.source,
                "sequence": item.sequence,
                "event_sequence": item.event_sequence,
                "version": item.version,
                "phase": item.phase,
                "day": item.day,
                "event_type": item.event_type,
                "actor_id": item.actor_id,
                "occurred_at": _format_datetime(item.occurred_at),
                "payload": item.payload,
            }
        )


def _timeline_title(item: TimelineItem, language: Language) -> str:
    translated = text(language, item.headline_key)
    if item.actor_id and item.headline_key in {
        "timeline_headline_player_spoke",
        "timeline_headline_vote_cast",
    }:
        return f"{translated}: {item.actor_id}"
    return translated


def _render_events_panel(events: GameEventsResponse | None, *, language: Language) -> None:
    with st.expander(text(language, "public_events"), expanded=False):
        if events is None or not events.events:
            st.info(text(language, "events_empty"))
            return
        rows = [
            {
                "sequence": event.sequence,
                "day": event.day or "",
                "phase": event.phase or "",
                "event_type": event.event_type,
                "actor_id": event.actor_id or "",
                "occurred_at": _format_datetime(event.occurred_at),
            }
            for event in events.events
        ]
        st.dataframe(rows, width="stretch", hide_index=True)
        for event in events.events:
            with st.expander(f"{text(language, 'event_detail')} #{event.sequence}"):
                st.json(event.model_dump(mode="json"))


def _render_observer_hint(
    hint: ObserverHint,
    state: PublicGameState,
    *,
    language: Language,
) -> None:
    with st.container(border=True):
        st.subheader(text(language, "observer_hint"))
        st.markdown(f"**{text(language, hint.title_key).format(day=state.day)}**")
        st.write(text(language, hint.body_key))
        for bullet_key in hint.bullet_keys:
            st.markdown(f"- {text(language, bullet_key)}")
        st.info(text(language, hint.next_key))


def _render_player_status_panel(state: PublicGameState, *, language: Language) -> None:
    with st.container(border=True):
        st.subheader(text(language, "player_status"))
        for row in build_player_status_rows(state, human_player_id=_session_player_id()):
            relation = f" ({text(language, row.relation_key)})" if row.relation_key else ""
            status_class = "alive" if row.alive else "dead"
            st.markdown(
                f"""
                <div class="wa-player-row">
                  <span class="wa-player-dot {status_class}"></span>
                  <span class="wa-player-name">
                    {_escape(row.name)} <span class="wa-player-id">{_escape(row.player_id)}</span>
                    {_escape(relation)}
                  </span>
                  <span class="wa-player-status {status_class}">
                    {_escape(text(language, row.status_key))}
                  </span>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_human_action_panel(
    *,
    client: GameApiClient,
    language: Language,
    state: PublicGameState,
) -> None:
    with st.container(border=True):
        st.subheader(text(language, "human_action"))
        st.caption(text(language, "token_help"))
        player_ids = [player.id for player in state.players]
        player_id = str(
            st.selectbox(
                text(language, "player_id"),
                player_ids,
                index=(
                    player_ids.index(_session_player_id())
                    if _session_player_id() in player_ids
                    else 0
                ),
            )
        )
        st.session_state["human_player_id"] = player_id
        token_default = _session_control_tokens().get(player_id, "")
        control_token = str(
            st.text_input(
                text(language, "control_token"),
                value=token_default,
                type="password",
            )
        )
        if control_token:
            control_tokens = _session_control_tokens()
            control_tokens[player_id] = control_token
            st.session_state["control_tokens"] = control_tokens
        if st.button(text(language, "clear_token")):
            control_tokens = _session_control_tokens()
            control_tokens.pop(player_id, None)
            st.session_state["control_tokens"] = control_tokens
            st.session_state["last_observation"] = None
            st.rerun()

        if st.button(text(language, "show_observation")) and control_token:
            observation = _safe_call(
                language,
                lambda: workflows.get_private_observation(
                    client,
                    state.game_id,
                    player_id,
                    control_token=control_token,
                ),
            )
            if observation is not None:
                st.session_state["last_observation"] = observation
                st.success(text(language, "observation_loaded"))

        observation = _session_observation()
        if observation is not None:
            st.markdown(f"**{text(language, 'observation')}**")
            st.json(observation.observation)
            _render_action_composer(
                client=client,
                language=language,
                state=state,
                player_id=player_id,
                control_token=control_token,
                observation=observation,
            )


def _render_action_composer(
    *,
    client: GameApiClient,
    language: Language,
    state: PublicGameState,
    player_id: str,
    control_token: str,
    observation: PrivateObservationResponse,
) -> None:
    raw_actions = observation.observation.get("available_actions", [])
    actions = [str(action) for action in raw_actions] if isinstance(raw_actions, list) else []
    if not actions:
        return
    action_type = str(st.selectbox(text(language, "action_type"), actions))
    target_id = None
    message = None
    if action_type == "speech":
        message = str(st.text_area(text(language, "action_message"), value=""))
    elif action_type != "pass":
        target_options = [player.id for player in state.players if player.id != player_id]
        if target_options:
            target_id = str(st.selectbox(text(language, "action_target"), target_options))
    reason = str(st.text_area(text(language, "action_reason"), value=""))
    if st.button(text(language, "submit_action"), type="primary") and control_token:
        request = SubmitPlayerActionRequest(
            type=cast(Any, action_type),
            target_id=target_id,
            message=message,
            reason=reason,
        )
        submitted = _safe_call(
            language,
            lambda: workflows.submit_player_action(
                client,
                state.game_id,
                player_id,
                request,
                control_token=control_token,
            ),
        )
        if submitted is not None:
            logger.info(
                LOG_STREAMLIT_ACTION_SUBMITTED,
                extra={
                    "game_id": state.game_id,
                    "player_id": player_id,
                    "action_type": action_type,
                },
            )
            st.session_state["last_observation"] = None
            st.success(text(language, "action_submitted"))
            st.rerun()


def _render_update_panel(
    *,
    auto_refresh: bool,
    last_refreshed_at: datetime,
    language: Language,
) -> None:
    with st.container(border=True):
        st.subheader(text(language, "refresh_panel"))
        st.caption(text(language, "auto_refresh_on" if auto_refresh else "auto_refresh_off"))
        if st.button(text(language, "refresh_latest"), width="stretch"):
            logger.info(LOG_STREAMLIT_REFRESHED, extra={"trigger": "panel"})
            st.rerun()
        st.caption(f"{text(language, 'last_refreshed')}: {_format_clock(last_refreshed_at)}")


def _render_runs_panel(runs: GameRunsResponse | None, *, language: Language) -> None:
    with st.container(border=True):
        st.subheader(text(language, "recent_runs"))
        if runs is None or not runs.runs:
            st.info(text(language, "runs_empty"))
            return
        rows = [
            {
                "game_id": run.game_id,
                "status": run.status,
                "phase": run.phase,
                "day": run.day,
                "winner": run.winner or "",
                "players": run.player_count,
                "alive": run.alive_count,
                "turns": run.turn_count,
                "updated_at": _format_datetime(run.updated_at),
            }
            for run in runs.runs
        ]
        st.dataframe(rows, width="stretch", hide_index=True)


def _load_runs(
    client: GameApiClient,
    settings: AppSettings,
    language: Language,
) -> GameRunsResponse | None:
    return _safe_call(
        language,
        lambda: workflows.list_games(client, limit=settings.streamlit_run_limit),
    )


def _safe_call(language: Language, action: Callable[[], T]) -> T | None:
    try:
        return action()
    except AppError as exc:
        logger.warning(LOG_STREAMLIT_APPLICATION_ERROR_HANDLED, extra=exc.log_extra())
        st.error(exc.detail or text(language, "api_unavailable"))
        return None


def _timeline_items(
    *,
    turns: GameTurnsResponse | None,
    events: GameEventsResponse | None,
) -> list[TimelineItem]:
    if turns is not None and turns.turns:
        return build_timeline_items_from_turns(turns.turns)
    if events is not None and events.events:
        return build_timeline_items_from_events(events.events)
    return []


def _turn_count_for_game(
    *,
    runs: GameRunsResponse | None,
    game_id: str,
    fallback: int,
) -> int:
    if runs is None:
        return fallback
    for run in runs.runs:
        if run.game_id == game_id:
            return run.turn_count
    return fallback


def _phase_label(phase: str | None, day: int | None, language: Language) -> str:
    style = resolve_phase_style(phase)
    label = text(language, style.label_key)
    if phase in {"day_discussion", "voting", "night"} and day is not None:
        return f"{label} {day}"
    return label


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _format_clock(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone().strftime("%H:%M:%S")


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _session_control_tokens() -> dict[str, str]:
    raw_tokens = st.session_state.get("control_tokens", {})
    if not isinstance(raw_tokens, dict):
        return {}
    return {str(key): str(value) for key, value in raw_tokens.items()}


def _session_player_id() -> str:
    return str(st.session_state.get("human_player_id", "player-1"))


def _session_observation() -> PrivateObservationResponse | None:
    raw_observation = st.session_state.get("last_observation")
    if isinstance(raw_observation, PrivateObservationResponse):
        return raw_observation
    return None


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        header[data-testid="stHeader"],
        div[data-testid="stToolbar"] {
            display: none;
        }
        .block-container {
            padding-top: 1.15rem;
            padding-bottom: 2.0rem;
            max-width: 1500px;
        }
        section[data-testid="stSidebar"] {
            background: #fbfbfc;
            border-right: 1px solid #e5e7eb;
        }
        .wa-sidebar-brand {
            display: flex;
            align-items: center;
            gap: 0.85rem;
            padding: 0.35rem 0 0.9rem;
            border-bottom: 1px solid #e5e7eb;
            margin-bottom: 1.0rem;
        }
        .wa-brand-mark {
            width: 42px;
            height: 42px;
            border-radius: 8px;
            background: #b11226;
            color: #fff;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 1.15rem;
        }
        .wa-brand-title {
            font-size: 1.1rem;
            font-weight: 750;
            color: #111827;
            line-height: 1.15;
        }
        .wa-brand-caption {
            color: #6b7280;
            font-size: 0.82rem;
            margin-top: 0.18rem;
        }
        .wa-metric-card {
            min-height: 74px;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 0.72rem 0.85rem;
            background: #ffffff;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        .wa-metric-label {
            font-size: 0.74rem;
            color: #6b7280;
            line-height: 1.2;
            margin-bottom: 0.22rem;
        }
        .wa-metric-value {
            color: #111827;
            font-size: 1.15rem;
            font-weight: 760;
            line-height: 1.25;
            overflow-wrap: anywhere;
        }
        .stButton > button[kind="primary"] {
            background: #b11226;
            border-color: #b11226;
        }
        .wa-timeline-row {
            display: grid;
            grid-template-columns: minmax(86px, 110px) minmax(0, 1fr);
            column-gap: 0.8rem;
            align-items: stretch;
            margin: 0.62rem 0;
        }
        .wa-timeline-marker {
            border-right: 2px solid #d1d5db;
            padding: 0.35rem 0.75rem 0.35rem 0;
            text-align: right;
        }
        .wa-phase-pill {
            border: 1px solid currentColor;
            border-radius: 8px;
            padding: 0.32rem 0.45rem;
            font-weight: 740;
            display: inline-block;
            min-width: 68px;
            text-align: center;
            background: #fff;
        }
        .wa-timeline-time {
            margin-top: 0.32rem;
            color: #6b7280;
            font-size: 0.78rem;
        }
        .wa-timeline-card {
            position: relative;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            background: #fff;
            min-height: 86px;
            overflow: hidden;
        }
        .wa-timeline-card-accent {
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 4px;
        }
        .wa-timeline-content {
            padding: 0.82rem 0.95rem 0.76rem 1.05rem;
        }
        .wa-timeline-title {
            color: #111827;
            font-weight: 760;
            font-size: 1.02rem;
            line-height: 1.35;
        }
        .wa-timeline-summary {
            color: #374151;
            font-size: 0.88rem;
            line-height: 1.45;
            margin-top: 0.18rem;
        }
        .wa-timeline-meta {
            color: #6b7280;
            font-size: 0.74rem;
            margin-top: 0.34rem;
            overflow-wrap: anywhere;
        }
        .wa-player-row {
            display: grid;
            grid-template-columns: 16px minmax(0, 1fr) auto;
            gap: 0.48rem;
            align-items: center;
            border-bottom: 1px solid #edf2f7;
            padding: 0.38rem 0;
        }
        .wa-player-row:last-child { border-bottom: 0; }
        .wa-player-dot {
            width: 10px;
            height: 10px;
            border-radius: 999px;
            display: inline-block;
        }
        .wa-player-dot.alive { background: #0f766e; }
        .wa-player-dot.dead { background: #dc2626; }
        .wa-player-name {
            color: #111827;
            font-size: 0.87rem;
            overflow-wrap: anywhere;
        }
        .wa-player-id {
            color: #6b7280;
            font-size: 0.76rem;
        }
        .wa-player-status {
            border-radius: 6px;
            padding: 0.1rem 0.38rem;
            font-size: 0.72rem;
            white-space: nowrap;
        }
        .wa-player-status.alive {
            background: #ccfbf1;
            color: #0f766e;
        }
        .wa-player-status.dead {
            background: #fee2e2;
            color: #b91c1c;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 8px;
        }
        @media (max-width: 900px) {
            .wa-timeline-row {
                grid-template-columns: 1fr;
            }
            .wa-timeline-marker {
                border-right: 0;
                text-align: left;
                padding-right: 0;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


_INVALID_INTEGER = object()


def _parse_optional_int(
    value: str,
    *,
    label: str,
    language: Language,
) -> int | None | object:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        st.sidebar.error(text(language, "invalid_integer").format(label=label))
        return _INVALID_INTEGER


if __name__ == "__main__":
    render_app()
