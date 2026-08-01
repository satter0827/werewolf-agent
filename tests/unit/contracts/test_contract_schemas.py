import pytest
from pydantic import ValidationError

from werewolf_agent.contracts.schemas import (
    PLAYER_ACTION_REQUEST_ADAPTER,
    GameSetupSelectionRequest,
    SavedSetupRequest,
)


def test_saved_setup_selection_requires_an_explicit_revision() -> None:
    selection = SavedSetupRequest(mode="saved", setup_id="setup-1", revision=3)

    assert selection.revision == 3

    with pytest.raises(ValidationError):
        SavedSetupRequest.model_validate({"mode": "saved", "setup_id": "setup-1"})


def test_setup_selection_is_discriminated_by_mode() -> None:
    from pydantic import TypeAdapter

    selection = TypeAdapter(GameSetupSelectionRequest).validate_python(
        {"mode": "template", "template_id": "standard_6"}
    )

    assert selection.mode == "template"


def test_setup_wire_models_reject_unknown_fields() -> None:
    """未知fieldを無視してschema適合入力へ見せない。"""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        SavedSetupRequest.model_validate(
            {
                "mode": "saved",
                "setup_id": "setup-1",
                "revision": 3,
                "unknown": True,
            }
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "type": "speech",
            "utterance": "   ",
            "topic_id": "p2",
            "position": "support",
            "relation": "independent",
        },
        {
            "type": "speech",
            "utterance": "発言",
            "topic_id": " ",
            "position": "support",
            "relation": "independent",
        },
        {"type": "vote", "target_id": "p2", "reason": "\t"},
        {"type": "use_ability", "ability_id": " ", "target_id": None},
    ],
)
def test_player_action_wire_rejects_blank_structured_fields(payload: dict[str, object]) -> None:
    """空白だけのIDと文言を非同期command受付前に拒否する."""
    with pytest.raises(ValidationError, match="string_too_short"):
        PLAYER_ACTION_REQUEST_ADAPTER.validate_python(payload)
