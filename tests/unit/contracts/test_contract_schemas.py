import pytest
from pydantic import ValidationError

from werewolf_agent.contracts.schemas import GameSetupSelectionRequest, SavedSetupRequest


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
