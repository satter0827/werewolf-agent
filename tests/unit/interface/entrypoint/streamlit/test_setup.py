from werewolf_agent.contracts.schemas import LocalRulesSettings, RulesetResponse
from werewolf_agent.interface.entrypoint.streamlit import setup
from werewolf_agent.interface.entrypoint.streamlit.i18n import load_i18n
from werewolf_agent.interface.runtime import AppSettings


def _catalog():
    return load_i18n(AppSettings(_env_file=None))


def test_setup_defaults_use_ruleset_role_counts_and_rules() -> None:
    session: dict[str, object] = {}
    ruleset = _ruleset()

    assert setup.current_view(session) == setup.VIEW_SETUP
    setup.switch_view(session, setup.VIEW_OBSERVER_SETUP)
    assert setup.current_view(session) == setup.VIEW_OBSERVER_SETUP
    assert setup.role_counts(session, ruleset) == {"werewolf": 1, "villager": 4}
    assert setup.rules(session, ruleset) == _rules()


def test_setup_role_counts_drive_validation_and_seats() -> None:
    ruleset = _ruleset()
    counts = {"werewolf": 1, "villager": 4}

    validation = setup.validate_setup(counts, ruleset, catalog=_catalog(), lang="ja")

    assert validation.is_valid is True
    assert setup.seat_options(counts) == [
        ("player-1", "P1"),
        ("player-2", "P2"),
        ("player-3", "P3"),
        ("player-4", "P4"),
        ("player-5", "P5"),
    ]


def test_setup_validation_rejects_missing_faction_and_out_of_range_total() -> None:
    ruleset = _ruleset()

    validation = setup.validate_setup({"villager": 9}, ruleset, catalog=_catalog(), lang="ja")

    assert validation.is_valid is False
    assert "合計人数は 5〜8 人にしてください。" in validation.messages
    assert "人狼陣営を 1 人以上にしてください。" in validation.messages


def test_setup_remembers_settings_and_parses_optional_seed() -> None:
    session: dict[str, object] = {}
    rules = _rules().model_copy(update={"enable_first_night_attack": False})

    setup.remember_role_counts(session, {"werewolf": 1, "villager": 5})
    setup.remember_rules(session, rules)
    setup.remember_seed_text(session, "  ")

    assert setup.role_counts(session, _ruleset()) == {"werewolf": 1, "villager": 5}
    assert setup.rules(session, _ruleset()) == rules
    assert setup.seed_from_text(setup.seed_text(session, default_seed=1)) is None


def _ruleset() -> RulesetResponse:
    return RulesetResponse(
        player_count={"min": 5, "max": 8},
        roles=[
            {"id": "werewolf", "name": "人狼", "faction": "werewolf", "abilities": []},
            {"id": "villager", "name": "村人", "faction": "village", "abilities": []},
        ],
        default_role_counts={"werewolf": 1, "villager": 4},
        default_rules=_rules(),
    )


def _rules() -> LocalRulesSettings:
    return LocalRulesSettings(
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
