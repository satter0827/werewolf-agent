from werewolf_agent.configuration import AppSettings
from werewolf_agent.contracts.schemas import GameSetupOptionsResponse, LocalRulesSettings
from werewolf_agent.interfaces.streamlit import setup
from werewolf_agent.interfaces.streamlit.i18n import load_i18n


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
    setup.remember_agent_strategy_id(session, "target_ranker")
    setup.remember_seed_text(session, "  ")

    assert setup.role_counts(session, _setup_options()) == {"werewolf": 1, "villager": 5}
    assert setup.rules(session, _setup_options()) == rules
    assert setup.selected_agent_strategy_id(session, _setup_options()) == "target_ranker"
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


def _setup_options() -> GameSetupOptionsResponse:
    return GameSetupOptionsResponse(
        player_count={"min": 5, "max": 8},
        roles=[
            {"id": "werewolf", "name": "人狼", "faction": "werewolf", "abilities": []},
            {"id": "villager", "name": "村人", "faction": "village", "abilities": []},
        ],
        default_role_counts={"werewolf": 1, "villager": 4},
        default_rules=_rules(),
        default_agent_strategy_id="stable_fast",
        agent_strategies=[
            {
                "id": "stable_fast",
                "name": "Stable Fast",
                "description": "Fast fallback strategy.",
            },
            {
                "id": "target_ranker",
                "name": "Target Ranker",
                "description": "Ranks legal targets.",
            },
        ],
    )


def _rules() -> LocalRulesSettings:
    return LocalRulesSettings(
        day_speech_limit_per_player=1,
        allow_self_vote=False,
        allow_vote_revision=False,
        allow_night_action_revision=False,
        enable_first_night_attack=True,
        enable_no_elimination_on_tie=True,
        enable_random_elimination_on_tie=False,
        allow_knight_self_guard=True,
        allow_knight_repeat_guard=True,
        allow_seer_self_inspect=False,
        allow_werewolf_friendly_fire=False,
        reveal_role_on_death=False,
    )
