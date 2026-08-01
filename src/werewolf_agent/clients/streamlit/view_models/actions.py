"""actions projections for the Streamlit game screen."""

from __future__ import annotations

from werewolf_agent.clients.streamlit.i18n import I18nCatalog, Language
from werewolf_agent.clients.streamlit.icons import action_icon
from werewolf_agent.clients.streamlit.view_models.formatting import _player_name
from werewolf_agent.clients.streamlit.view_models.types import (
    ActionChoiceView,
    HandPanelView,
    ObservationView,
    ScreenMode,
)
from werewolf_agent.contracts.schemas import (
    GAME_STATUS_COMPLETED,
    PlayerObservation,
    PlayerObservationResponse,
    PublicGameState,
)


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
    role = observation.me.role
    actions: list[tuple[str, str | None]] = [
        (item.type, item.ability_id) for item in observation.available_actions
    ]
    action_keys = [
        f"{action_type}:{ability_id}" if ability_id else action_type
        for action_type, ability_id in actions
    ]
    known_role_lines = [
        f"{_player_name(state.players, player_id)}: "
        f"{_theme_term(state, 'role_names', role_id, catalog.label(lang, 'role', role_id))}"
        for player_id, role_id in sorted(observation.known_roles.items())
    ]
    target_candidates = {
        action: target_candidates_for_action(
            action,
            state=state,
            observation=observation,
            manual_player_id=manual_player_id,
        )
        for action in action_keys
    }
    speech_by_id = {speech.speech_id: speech for speech in observation.history.speeches}
    reference_choices = {
        reference_id: (
            f"{_player_name(state.players, speech_by_id[reference_id].player_id)}: "
            f"{speech_by_id[reference_id].message}"
        )
        for reference_id in (
            observation.discussion_round.reference_ids
            if observation.discussion_round is not None
            else ()
        )
        if reference_id in speech_by_id and speech_by_id[reference_id].player_id != manual_player_id
    }
    return ObservationView(
        role=_theme_term(state, "role_names", role, catalog.label(lang, "role", role)),
        available_actions=action_keys,
        action_choices=[
            action_choice(
                action_type,
                catalog,
                lang,
                ability_id=ability_id,
                requires_target=bool(
                    target_candidates[f"{action_type}:{ability_id}" if ability_id else action_type]
                ),
                label=(
                    _theme_term(
                        state,
                        "ability_names",
                        ability_id,
                        str(ability_id),
                    )
                    if ability_id
                    else _theme_term(
                        state,
                        "action_names",
                        action_type,
                        catalog.label(lang, "action", action_type),
                    )
                ),
            )
            for action_type, ability_id in actions
        ],
        known_role_lines=known_role_lines,
        target_candidates=target_candidates,
        reference_choices=reference_choices,
    )


def action_choice(
    action_type: str,
    catalog: I18nCatalog,
    lang: Language,
    *,
    ability_id: str | None = None,
    requires_target: bool,
    label: str | None = None,
) -> ActionChoiceView:
    """Return display metadata for one action."""
    return ActionChoiceView(
        action_type=f"{action_type}:{ability_id}" if ability_id else action_type,
        ability_id=ability_id,
        icon=action_icon(action_type).symbol,
        label=label or catalog.label(lang, "action", action_type),
        requires_target=requires_target,
        requires_message=action_type == "speech",
    )


def _theme_term(
    state: PublicGameState,
    field: str,
    concept_id: str | None,
    fallback: str,
) -> str:
    """Resolve a presentation term from the game theme without changing mechanics IDs."""
    if concept_id is None or state.theme is None:
        return fallback
    terms = getattr(state.theme, field)
    return str(terms.get(concept_id, fallback))


def _winner_label(state: PublicGameState, catalog: I18nCatalog, lang: Language) -> str:
    """Return the selected theme's winning faction label."""
    fallback = catalog.label(lang, "winner", state.winner)
    if state.winner is None:
        return fallback
    return _theme_term(state, "faction_names", state.winner, fallback)


def target_candidates_for_action(
    action_type: str,
    *,
    state: PublicGameState,
    observation: PlayerObservation,
    manual_player_id: str | None,
) -> list[str]:
    """Return visible player ids that can be offered as target candidates."""
    _ = state, manual_player_id
    descriptor = next(
        (item for item in observation.available_actions if item.key == action_type),
        None,
    )
    return [] if descriptor is None else list(descriptor.legal_target_ids)


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
                winner=_winner_label(state, catalog, lang),
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
        labels = " / ".join(choice.label for choice in observation.action_choices)
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
            winner=_winner_label(state, catalog, lang),
        )
    if screen_mode == "observer":
        return catalog.t(lang, "game.observer.detail")
    if observation is not None and observation.available_actions:
        labels = " / ".join(choice.label for choice in observation.action_choices)
        return labels
    return catalog.t(lang, "game.play.waiting.detail")


def _has_available_actions(observation: ObservationView | None) -> bool:
    return observation is not None and bool(observation.available_actions)
