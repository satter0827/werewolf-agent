import pytest
from pydantic import ValidationError

from werewolf_agent.contracts import CreateGameRequest


def test_create_game_request_rejects_duplicate_custom_role_abilities() -> None:
    with pytest.raises(ValidationError, match="custom role abilities must be unique"):
        CreateGameRequest(
            role_counts={"werewolf": 1, "villager": 4},
            custom_roles=[
                {
                    "id": "custom_reader",
                    "name": "Reader",
                    "faction": "village",
                    "abilities": ["inspect", "inspect"],
                    "difficulty": 2,
                }
            ],
        )


def test_create_game_request_validates_day_speech_limit_rule() -> None:
    with pytest.raises(ValidationError, match="day_speech_limit_per_player"):
        CreateGameRequest(
            role_counts={"werewolf": 1, "villager": 4},
            rules={
                "day_speech_limit_per_player": 0,
                "allow_self_vote": False,
                "allow_vote_revision": False,
                "allow_night_action_revision": False,
                "enable_first_night_attack": True,
                "enable_no_elimination_on_tie": True,
                "enable_random_elimination_on_tie": False,
                "allow_knight_self_guard": True,
                "allow_knight_repeat_guard": True,
                "allow_seer_self_inspect": False,
                "allow_werewolf_friendly_fire": False,
                "reveal_role_on_death": False,
            },
        )
