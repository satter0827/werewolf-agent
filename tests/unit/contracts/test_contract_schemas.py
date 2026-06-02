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
