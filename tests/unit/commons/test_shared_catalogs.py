import pytest

from werewolf_agent.commons.shared.messages import (
    MESSAGE_CHARACTER_ASSIGNMENTS_KEYS_MUST_MATCH_PLAYERS,
    MESSAGE_GENERATED_PLAYER_INDEX_MUST_BE_AT_LEAST_ONE,
    MESSAGE_INVALID_VALUE,
    message_field_must_be_one_of,
    message_invalid_llm_decision,
)
from werewolf_agent.commons.shared.validation import (
    generated_player_id,
    generated_player_ids,
    generated_player_name,
    non_blank,
    normalize_choice,
    public_generated_player_label,
    public_generated_player_name_label,
)


def test_shared_validation_uses_catalog_messages() -> None:
    with pytest.raises(ValueError, match="name must not be blank"):
        non_blank(" ", "name")

    with pytest.raises(ValueError, match="mode must be one of: a, b"):
        normalize_choice("c", field_name="mode", choices={"a", "b"}, case="lower")

    assert message_field_must_be_one_of("mode", {"b", "a"}) == "mode must be one of: a, b"
    assert MESSAGE_INVALID_VALUE == "Invalid value."
    assert (
        MESSAGE_CHARACTER_ASSIGNMENTS_KEYS_MUST_MATCH_PLAYERS
        == "character_assignments keys must match generated player ids"
    )
    assert message_invalid_llm_decision("ValidationError") == (
        "invalid llm decision: ValidationError"
    )


def test_generated_player_helpers_share_id_and_label_contracts() -> None:
    with pytest.raises(ValueError, match=MESSAGE_GENERATED_PLAYER_INDEX_MUST_BE_AT_LEAST_ONE):
        generated_player_id(0)

    assert generated_player_id(3) == "player-3"
    assert generated_player_name(3) == "Player 3"
    assert generated_player_ids(3) == {"player-1", "player-2", "player-3"}
    assert public_generated_player_label("player-3") == "P3"
    assert public_generated_player_name_label("Player 3") == "P3"
