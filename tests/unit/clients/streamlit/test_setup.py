from typing import Any

from werewolf_agent.clients.streamlit import setup
from werewolf_agent.clients.streamlit.i18n import load_i18n
from werewolf_agent.clients.streamlit.screens import load_screen_catalog
from werewolf_agent.clients.streamlit.views.setup import SETUP_STEP_BY_ELEMENT, _select_policy
from werewolf_agent.contracts.schemas import (
    GameSetupOptionsResponse,
    LocalRulesSettings,
    RulePhaseOrderOptionView,
)
from werewolf_agent.settings import AppSettings


def _catalog():
    return load_i18n(AppSettings(_env_file=None))


def test_setup_defaults_use_setup_options_role_counts_and_rules() -> None:
    session: dict[str, object] = {}
    setup_options = _setup_options()

    assert setup.current_view(session) == setup.VIEW_PLAY_SETUP
    setup.switch_view(session, setup.VIEW_OBSERVE_SETUP)
    assert setup.current_view(session) == setup.VIEW_OBSERVE_SETUP
    assert setup.role_counts(session, setup_options) == {"werewolf": 1, "villager": 4}
    assert setup.rules(session, setup_options) == _rules()


def test_view_transition_requests_one_scroll_reset() -> None:
    session: dict[str, object] = {}

    setup.switch_view(session, setup.VIEW_OBSERVE_SETUP)

    assert setup.consume_pending_view_scroll(session) is True
    assert setup.consume_pending_view_scroll(session) is False

    setup.switch_view(session, setup.VIEW_OBSERVE_SETUP)

    assert setup.consume_pending_view_scroll(session) is False


def test_setup_role_counts_drive_validation_and_seats() -> None:
    setup_options = _setup_options()
    counts = {"werewolf": 1, "villager": 4}

    validation = setup.validate_setup(counts, setup_options, catalog=_catalog(), lang="ja")

    assert validation.is_valid is True
    assert setup.seat_options(counts) == [
        ("player-1", "P1"),
        ("player-2", "P2"),
        ("player-3", "P3"),
        ("player-4", "P4"),
        ("player-5", "P5"),
    ]


def test_setup_validation_rejects_missing_faction_and_out_of_range_total() -> None:
    setup_options = _setup_options()

    validation = setup.validate_setup({"villager": 9}, setup_options, catalog=_catalog(), lang="ja")

    assert validation.is_valid is False
    assert "合計人数は 5〜8 人にしてください。" in validation.messages


def test_setup_remembers_settings_and_parses_optional_seed() -> None:
    session: dict[str, object] = {}
    rules = _rules().model_copy(update={"enable_first_night_attack": False})

    setup.remember_role_counts(session, {"werewolf": 1, "villager": 5})
    setup.remember_rules(session, rules)
    setup.remember_seed_text(session, "  ")

    assert setup.role_counts(session, _setup_options()) == {"werewolf": 1, "villager": 5}
    assert setup.rules(session, _setup_options()) == rules
    assert setup.seed_from_text(setup.seed_text(session, default_seed=1)) is None


def test_setup_draft_and_preferences_use_single_session_models() -> None:
    session: dict[str, object] = {}

    setup.remember_role_counts(session, {"werewolf": 1, "villager": 5})
    setup.remember_seed_text(session, "42")
    setup.remember_manual_player_id(session, "player-2")
    setup.remember_preferred_language(session, "en")

    assert set(session) == {
        setup.KEY_GAME_SETUP_DRAFT,
        setup.KEY_STREAMLIT_PREFERENCES,
    }
    assert setup.game_setup_draft(session).manual_player_id == "player-2"
    assert setup.preferred_language(session, "ja") == "en"


def test_phase_order_selector_matches_default_by_phase_sequence() -> None:
    streamlit = _PolicySelectorStub()
    default_phases = ("night", "day_discussion", "voting")
    options = [
        RulePhaseOrderOptionView(
            id="reverse",
            name="逆順",
            description="投票から始めます。",
            phases=("voting", "day_discussion", "night"),
        ),
        RulePhaseOrderOptionView(
            id="classic",
            name="標準順",
            description="夜から始めます。",
            phases=default_phases,
        ),
    ]

    selected = _select_policy(
        streamlit,
        "phase順序",
        options,
        default_phases,
        empty_message="選択肢がありません: {label}",
    )

    assert selected == default_phases
    assert streamlit.selected_index == 1


def test_every_configured_setup_main_element_is_assigned_to_a_step() -> None:
    screens = load_screen_catalog(AppSettings(_env_file=None))
    configured = {
        element.id for element in screens.elements("setup", "main") if element.id != "header"
    }

    assert configured == set(SETUP_STEP_BY_ELEMENT)


class _PolicySelectorStub:
    selected_index = -1

    def selectbox(self, label: str, options: list[str], **kwargs: Any) -> str:
        self.selected_index = int(kwargs["index"])
        return options[self.selected_index]

    def caption(self, value: str) -> None:
        pass


def _setup_options() -> GameSetupOptionsResponse:
    return GameSetupOptionsResponse(
        player_count={"min": 5, "max": 8},
        roles=[
            {
                "id": "werewolf",
                "name": "人狼",
                "identity_faction": "werewolf",
                "victory_team": "werewolf",
                "objective": "村側と同数になります",
                "abilities": [],
            },
            {
                "id": "villager",
                "name": "村人",
                "identity_faction": "village",
                "victory_team": "village",
                "objective": "人狼を排除します",
                "abilities": [],
            },
        ],
        default_role_counts={"werewolf": 1, "villager": 4},
        default_rules=_rules(),
    )


def _rules() -> LocalRulesSettings:
    return LocalRulesSettings(
        day_speech_limit_per_player=1,
        allow_self_vote=False,
        allow_vote_revision=False,
        allow_night_action_revision=False,
        enable_first_night_attack=True,
        vote_tie_resolution="no_elimination",
        wolf_attack_tie_resolution="random_target",
        seer_result_detail="faction",
        medium_result_detail="faction",
        starting_phase="night",
        allow_knight_self_guard=True,
        allow_knight_repeat_guard=True,
        allow_seer_self_inspect=False,
        allow_werewolf_friendly_fire=False,
        reveal_role_on_death=False,
    )
