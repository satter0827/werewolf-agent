import pytest
from pydantic import ValidationError

from werewolf_agent.adapters.setup_options import get_local_setup_options
from werewolf_agent.clients.requests import build_custom_setup_request
from werewolf_agent.contracts import CreateGameRequest
from werewolf_agent.contracts.schemas import RuleCompositionSelection
from werewolf_agent.settings import AppSettings


def _valid_setup() -> dict[str, object]:
    options = get_local_setup_options(AppSettings(_env_file=None))
    preset = next(item for item in options.setup_presets if item.id == "standard_6")
    selection = build_custom_setup_request(
        setup_options=options,
        role_counts=dict(preset.role_counts),
        rules=options.default_rules,
        scenario_id=preset.scenario_id,
        character_assignments={},
        rule_composition=RuleCompositionSelection(),
    )
    return selection.setup.model_dump(mode="json")


def test_create_game_request_rejects_duplicate_custom_role_abilities() -> None:
    setup = _valid_setup()
    setup["mechanics"]["roles"]["seer"]["abilities"] = ["inspect", "inspect"]

    with pytest.raises(ValidationError, match="role abilities must be unique"):
        CreateGameRequest(setup={"mode": "custom", "setup": setup})


def test_create_game_request_validates_day_speech_limit_rule() -> None:
    setup = _valid_setup()
    setup["mechanics"]["rules"]["day_speech_limit_per_player"] = 0

    with pytest.raises(ValidationError, match="day_speech_limit_per_player"):
        CreateGameRequest(setup={"mode": "custom", "setup": setup})
