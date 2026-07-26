"""Playable Streamlit interface for one manual player."""

from __future__ import annotations

import logging
import secrets
from typing import Any, cast

from werewolf_agent.clients.presentation import implements_features
from werewolf_agent.clients.streamlit.i18n import (
    I18nCatalog,
    Language,
)
from werewolf_agent.clients.streamlit.operations import (
    load_setup_options,
)
from werewolf_agent.clients.streamlit.screens import (
    ScreenCatalog,
)
from werewolf_agent.clients.streamlit.setup import (
    character_assignments,
    custom_characters,
    custom_roles,
    narration_mode,
    remember_manual_player_id,
    remember_role_counts,
    remember_seed_text,
    role_counts,
    rules,
    seat_options,
    seed_from_text,
    seed_text,
    selected_manual_player_id,
    selected_scenario_id,
    selected_setup_preset_id,
    setup_options_with_session_customs,
    setup_summary,
    validate_setup,
)
from werewolf_agent.clients.streamlit.views.errors import render_app_error
from werewolf_agent.clients.streamlit.views.game import _create_game
from werewolf_agent.clients.streamlit.views.settings import (
    _ability_name,
    _has_duplicate_values,
    _narration_label,
    _render_character_assignments,
    _render_local_rules_settings,
    _render_narration_setup,
    _render_scenario_settings,
    _render_setup_preset_selector,
    _role_count_key,
    _scenario_name,
    _seat_index,
    _setup_preset_name,
)
from werewolf_agent.contracts import (
    AppError,
)
from werewolf_agent.contracts.schemas import (
    GameSetupOptionsResponse,
    LocalRulesSettings,
    NarrationMode,
    RuleCompositionSelection,
)
from werewolf_agent.settings import (
    AppSettings,
)

logger = logging.getLogger(__name__)
SETUP_STEP_BY_ELEMENT = {
    "preset": 0,
    "scenario": 0,
    "narration": 0,
    "role_counts": 1,
    "character_assignments": 2,
    "seed": 3,
    "local_rules": 3,
    "rule_composition": 3,
}
STREAMLIT_AUTH_SESSION_KEY = "_auth_session"


@implements_features("game_create")
def _render_setup_screen(
    st: Any,
    *,
    settings: AppSettings,
    catalog: I18nCatalog,
    lang: Language,
    observer: bool,
    screens: ScreenCatalog,
    mutations_available: bool = True,
) -> None:
    try:
        setup_options = setup_options_with_session_customs(
            st.session_state,
            load_setup_options(settings=settings),
        )
    except AppError as exc:
        render_app_error(st, exc, lang=lang)
        return

    seed_value = seed_text(st.session_state, settings.streamlit_default_seed)
    counts = role_counts(st.session_state, setup_options)
    rule_composition = setup_options.rule_composition.default
    if not mutations_available:
        st.warning(catalog.t(lang, "runtime.queue_required"))

    st.header(catalog.t(lang, "setup.title.observe" if observer else "setup.title.play"))
    st.caption(catalog.t(lang, "setup.mode.observe" if observer else "setup.mode.play"))
    steps = st.tabs(
        [
            "1. 世界観",
            "2. 役職",
            "3. 登場人物",
            "4. ルール",
        ]
    )
    for element in screens.elements("setup", "main"):
        if element.id == "header":
            continue
        step_index = SETUP_STEP_BY_ELEMENT.get(element.id)
        if step_index is None:
            continue
        with steps[step_index]:
            if element.id == "preset":
                _render_setup_preset_selector(
                    st, setup_options=setup_options, catalog=catalog, lang=lang
                )
            elif element.id == "scenario":
                _render_scenario_settings(
                    st, setup_options=setup_options, catalog=catalog, lang=lang
                )
            elif element.id == "narration":
                _render_narration_setup(st, setup_options=setup_options, catalog=catalog, lang=lang)
            elif element.id == "seed":
                seed_value = _render_seed_controls(
                    st,
                    settings,
                    catalog,
                    lang,
                    column_count=cast(int, screens.layout("setup").seed_columns),
                )
            elif element.id == "role_counts":
                counts = _render_role_counts(st, setup_options, catalog=catalog, lang=lang)
            elif element.id == "character_assignments":
                _render_character_assignments(
                    st,
                    setup_options=setup_options,
                    catalog=catalog,
                    lang=lang,
                )
            elif element.id == "local_rules":
                _render_local_rules_settings(
                    st, setup_options=setup_options, catalog=catalog, lang=lang
                )
            elif element.id == "rule_composition":
                rule_composition = _render_rule_composition(
                    st,
                    setup_options,
                    catalog=catalog,
                    lang=lang,
                )

    counts = role_counts(st.session_state, setup_options)
    active_rules = rules(st.session_state, setup_options)
    scenario_id = selected_scenario_id(st.session_state, setup_options)
    preset_id = selected_setup_preset_id(st.session_state, setup_options)
    active_narration_mode = narration_mode(st.session_state, setup_options)
    validation = validate_setup(counts, setup_options, catalog=catalog, lang=lang)
    total_players = sum(counts.values())
    manual_player_id = (
        None
        if observer
        else selected_manual_player_id(
            st.session_state,
            counts,
            default_player_id=settings.streamlit_default_manual_player_id,
        )
    )

    active_assignments = character_assignments(
        st.session_state,
        setup_options,
        player_count=total_players,
    )

    for element in screens.elements("setup", "summary"):
        if element.id == "summary_metrics":
            _render_setup_summary_metrics(
                st,
                setup_options=setup_options,
                scenario_id=scenario_id,
                preset_id=preset_id,
                narration_mode_value=active_narration_mode,
                total_players=total_players,
                column_count=cast(int, screens.layout("setup").summary_columns),
                catalog=catalog,
                lang=lang,
            )
        elif element.id == "validation_messages":
            _render_setup_validation_messages(
                st,
                validation=validation,
                seed_value=seed_value,
                catalog=catalog,
                lang=lang,
            )
        elif element.id == "manual_seat" and not observer:
            manual_player_id = _render_manual_seat_selector(
                st,
                counts,
                settings=settings,
                catalog=catalog,
                lang=lang,
            )
        elif element.id == "setup_summary":
            st.caption(
                setup_summary(
                    counts,
                    rules=active_rules,
                    setup_options=setup_options,
                    catalog=catalog,
                    lang=lang,
                )
            )

    for element in screens.elements("setup", "action"):
        if element.id == "submit":
            _render_setup_submit(
                st,
                settings=settings,
                counts=counts,
                rules_value=active_rules,
                seed_value=seed_value,
                observer=observer,
                manual_player_id=manual_player_id,
                validation=validation,
                scenario_id=scenario_id,
                setup_preset_id=preset_id,
                narration_mode_value=active_narration_mode,
                character_assignments_value=active_assignments,
                rule_composition=rule_composition,
                catalog=catalog,
                lang=lang,
                mutations_available=mutations_available,
            )


def _render_setup_summary_metrics(
    st: Any,
    *,
    setup_options: GameSetupOptionsResponse,
    scenario_id: str | None,
    preset_id: str | None,
    narration_mode_value: NarrationMode,
    total_players: int,
    column_count: int,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render configured setup summary metrics."""
    metrics = (
        (
            catalog.t(lang, "settings.scenario"),
            _scenario_name(setup_options, scenario_id, catalog, lang) if scenario_id else "-",
        ),
        (catalog.t(lang, "setup.total_players"), f"{total_players}"),
        (
            catalog.t(lang, "settings.narration"),
            _narration_label(narration_mode_value, catalog, lang),
        ),
    )
    columns = st.columns(column_count)
    for index, (label, value) in enumerate(metrics):
        columns[index % len(columns)].metric(label, value)
    if preset_id is not None:
        st.caption(_setup_preset_name(setup_options, preset_id, catalog, lang))


def _render_setup_validation_messages(
    st: Any,
    *,
    validation: Any,
    seed_value: str,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render setup validation messages."""
    for message in validation.messages:
        st.warning(message)
    try:
        seed_from_text(seed_value)
    except ValueError:
        st.warning(catalog.t(lang, "setup.seed_warning"))


def _render_setup_submit(
    st: Any,
    *,
    settings: AppSettings,
    counts: dict[str, int],
    rules_value: LocalRulesSettings,
    seed_value: str,
    observer: bool,
    manual_player_id: str | None,
    validation: Any,
    scenario_id: str | None,
    setup_preset_id: str | None,
    narration_mode_value: NarrationMode,
    character_assignments_value: dict[str, str],
    rule_composition: RuleCompositionSelection,
    catalog: I18nCatalog,
    lang: Language,
    mutations_available: bool,
) -> None:
    """Render the configured setup submit action."""
    disabled = (
        not mutations_available
        or not validation.is_valid
        or (manual_player_id is None and not observer)
        or scenario_id is None
        or _has_duplicate_values(character_assignments_value)
    )
    if not st.button(
        catalog.t(lang, "action.create_observer" if observer else "action.create_playable"),
        type="primary",
        use_container_width=True,
        disabled=disabled,
    ):
        return
    _create_game(
        st,
        feedback=st,
        settings=settings,
        role_counts=counts,
        rules=rules_value,
        seed_text=seed_value,
        manual_player_id=None if observer else str(manual_player_id),
        screen_mode="observer" if observer else "playable",
        scenario_id=scenario_id,
        setup_preset_id=setup_preset_id,
        narration_mode=narration_mode_value,
        character_assignments=character_assignments_value,
        custom_roles=custom_roles(st.session_state),
        custom_characters=custom_characters(st.session_state),
        rule_composition=rule_composition,
        catalog=catalog,
        lang=lang,
    )


def _render_rule_composition(
    st: Any,
    setup_options: GameSetupOptionsResponse,
    *,
    catalog: I18nCatalog,
    lang: Language,
) -> RuleCompositionSelection:
    """Render fixed policies as descriptions and multiple policies as selectors."""
    options = setup_options.rule_composition
    with st.expander(catalog.t(lang, "rules.advanced"), expanded=False):
        phase = _select_policy(
            st,
            catalog.t(lang, "rules.phase_order"),
            options.phase_orders,
            options.default.phases,
            empty_message=catalog.t(lang, "rules.options_empty"),
        )
        selected: dict[str, str] = {}
        for field, label, values in (
            ("action_policy", catalog.t(lang, "rules.action"), options.action_policies),
            (
                "resolution_policy",
                catalog.t(lang, "rules.resolution"),
                options.resolution_policies,
            ),
            ("phase_policy", catalog.t(lang, "rules.phase"), options.phase_policies),
            ("victory_policy", catalog.t(lang, "rules.victory"), options.victory_policies),
            (
                "visibility_policy",
                catalog.t(lang, "rules.visibility"),
                options.visibility_policies,
            ),
        ):
            selected[field] = _select_policy(
                st,
                label,
                values,
                getattr(options.default, field),
                empty_message=catalog.t(lang, "rules.options_empty"),
            )
    return RuleCompositionSelection(phases=phase, **selected)


def _select_policy(
    st: Any,
    label: str,
    options: list[Any],
    default: Any,
    *,
    empty_message: str,
) -> Any:
    if not options:
        raise AppError(empty_message.format(label=label))
    if len(options) == 1:
        option = options[0]
        st.markdown(f"**{label}: {option.name}**")
        st.caption(option.description)
        return getattr(option, "phases", option.id)
    ids = [option.id for option in options]
    default_id = default if isinstance(default, str) else ""
    if not default_id:
        default_phases = tuple(default)
        default_id = next(
            (
                option.id
                for option in options
                if tuple(getattr(option, "phases", ())) == default_phases
            ),
            ids[0],
        )
    selected_id = st.selectbox(
        label,
        ids,
        index=ids.index(default_id) if default_id in ids else 0,
        format_func=lambda value: next(item.name for item in options if item.id == value),
    )
    option = next(item for item in options if item.id == selected_id)
    st.caption(option.description)
    return getattr(option, "phases", option.id)


def _render_role_counts(
    st: Any,
    setup_options: GameSetupOptionsResponse,
    *,
    catalog: I18nCatalog,
    lang: Language,
) -> dict[str, int]:
    counts = role_counts(st.session_state, setup_options)
    st.subheader(catalog.t(lang, "setup.role_counts"))
    next_counts: dict[str, int] = {}
    for role in setup_options.roles:
        widget_key = _role_count_key(role.id)
        if widget_key not in st.session_state:
            st.session_state[widget_key] = int(counts.get(role.id, 0))
        ability_names = [
            _ability_name(setup_options, ability_id, catalog, lang) for ability_id in role.abilities
        ]
        next_counts[role.id] = int(
            st.number_input(
                role.name,
                min_value=0,
                max_value=setup_options.player_count["max"],
                step=1,
                key=widget_key,
                help=f"{catalog.label(lang, 'faction', role.identity_faction)} / "
                f"{', '.join(ability_names) if ability_names else catalog.t(lang, 'common.none')}",
            )
        )
    remember_role_counts(st.session_state, next_counts)
    return next_counts


def _render_manual_seat_selector(
    st: Any,
    counts: dict[str, int],
    *,
    settings: AppSettings,
    catalog: I18nCatalog,
    lang: Language,
) -> str | None:
    """Render the playable manual-seat selector."""
    seats = seat_options(counts)
    if not seats:
        st.warning(catalog.t(lang, "setup.no_seats"))
        return None
    current_player_id = selected_manual_player_id(
        st.session_state,
        counts,
        default_player_id=settings.streamlit_default_manual_player_id,
    )
    selected = st.selectbox(
        catalog.t(lang, "setup.seat"),
        seats,
        index=_seat_index(seats, current_player_id),
        format_func=lambda option: option[1],
    )
    remember_manual_player_id(st.session_state, selected[0])
    return str(selected[0])


def _render_seed_controls(
    st: Any,
    settings: AppSettings,
    catalog: I18nCatalog,
    lang: Language,
    *,
    column_count: int,
) -> str:
    seed = str(
        st.text_input(
            catalog.t(lang, "setup.seed"),
            value=seed_text(st.session_state, settings.streamlit_default_seed),
            help=catalog.t(lang, "setup.seed_help"),
        )
    )
    remember_seed_text(st.session_state, seed)
    seed_columns = st.columns(column_count)
    first_column, second_column = seed_columns[0], seed_columns[1]
    if first_column.button(catalog.t(lang, "action.random_seed"), use_container_width=True):
        remember_seed_text(
            st.session_state, str(secrets.randbelow(settings.streamlit_random_seed_max))
        )
        st.rerun()
    if second_column.button(catalog.t(lang, "action.unset_seed"), use_container_width=True):
        remember_seed_text(st.session_state, "")
        st.rerun()
    return seed
