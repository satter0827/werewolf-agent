import pytest

from werewolf_agent.adapters.llm.messages import message_invalid_llm_decision
from werewolf_agent.settings.messages import MESSAGE_INVALID_VALUE, message_field_must_be_one_of
from werewolf_agent.settings.validation import (
    non_blank,
    normalize_choice,
)


def test_settings_validation_uses_owned_messages() -> None:
    with pytest.raises(ValueError, match="name must not be blank"):
        non_blank(" ", "name")

    with pytest.raises(ValueError, match="mode must be one of: a, b"):
        normalize_choice("c", field_name="mode", choices={"a", "b"}, case="lower")

    assert message_field_must_be_one_of("mode", {"b", "a"}) == "mode must be one of: a, b"
    assert MESSAGE_INVALID_VALUE == "Invalid value."
    assert message_invalid_llm_decision("ValidationError") == (
        "invalid llm decision: ValidationError"
    )
